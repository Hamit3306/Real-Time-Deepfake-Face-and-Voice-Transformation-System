"""
GPU Worker - WebRTC VideoTransformTrack (v2 — Optimized)
=========================================================
aiortc kullanarak tarayıcıdan gelen WebRTC video akışını alır,
her kareye GPU üzerinde DeepFake uygular ve geri gönderir.

v2 değişiklikleri:
  - Adaptif frame-skipping: İşleme süresi arttıkça otomatik olarak kare atlar
  - Face bounding-box caching: Yüz algılamayı her karede yapmak yerine,
    son algılanan pozisyonu önbelleğe alır ve kısa aralıklarla günceller
  - İşleme süresi istatistikleri (loglama)
"""

import asyncio
import fractions
import logging
import time
from typing import Optional, Tuple

import av
import cv2
import numpy as np
from aiortc import MediaStreamTrack, VideoStreamTrack
from aiortc.contrib.media import MediaRelay

logger = logging.getLogger(__name__)

# FaceSwapper import — hem standalone hem de gpu_worker/ içinden çalışır
try:
    from modules.face_swap import FaceSwapper
except ModuleNotFoundError:
    import sys, os
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
    from modules.face_swap import FaceSwapper


# ---------------------------------------------------------------------------
# Global GPU kaynakları — yalnızca bir kez init edilir
# ---------------------------------------------------------------------------
_face_swapper: Optional[FaceSwapper] = None

def get_face_swapper() -> FaceSwapper:
    global _face_swapper
    if _face_swapper is None:
        logger.info("FaceSwapper başlatılıyor (GPU Worker)...")
        _face_swapper = FaceSwapper()
        _face_swapper.select_model("face1")   # Varsayılan persona
        logger.info("FaceSwapper hazır.")
    return _face_swapper


# ---------------------------------------------------------------------------
# Yardımcı dönüşüm fonksiyonları: aiortc VideoFrame <-> numpy (BGR)
# ---------------------------------------------------------------------------

def videoframe_to_ndarray(frame: av.VideoFrame) -> np.ndarray:
    """aiortc VideoFrame -> OpenCV BGR numpy dizisi."""
    return frame.to_ndarray(format="bgr24")


def ndarray_to_videoframe(img: np.ndarray, pts: int, time_base: fractions.Fraction) -> av.VideoFrame:
    """OpenCV BGR numpy dizisi -> aiortc VideoFrame."""
    img_rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
    new_frame = av.VideoFrame.from_ndarray(img_rgb, format="rgb24")
    new_frame.pts = pts
    new_frame.time_base = time_base
    return new_frame


# ---------------------------------------------------------------------------
# Face Bounding-Box Cache
# ---------------------------------------------------------------------------

class FaceBBoxCache:
    """
    Yüz algılama (detection) sonuçlarını önbelleğe alır.
    Her karede InsightFace detection çalıştırmak CPU/GPU pahalıdır.

    Strateji:
      - Her N karede bir tam face detection çalıştır
      - Aradaki karelerde son bilinen bounding-box bölgesini kullan
      - Yüz kaybolursa (detection sonucu boş) cache'i temizle

    Bu sayede FaceAnalysis.get() çağrısı ~60-70% azalır.
    """

    def __init__(self, detect_every_n: int = 3, bbox_expand_ratio: float = 0.15):
        self._detect_every_n  = detect_every_n     # Her N karede bir tam detection
        self._bbox_expand     = bbox_expand_ratio   # BBox'ı %15 genişlet (hareket toleransı)
        self._frame_count     = 0
        self._cached_faces    = None                # Son algılanan faces listesi
        self._cached_bbox     = None                # (x1, y1, x2, y2) bounding box
        self._last_detect_ts  = 0.0
        self._cache_hits      = 0
        self._cache_misses    = 0

    def should_detect(self) -> bool:
        """Bu karede tam detection çalıştırılmalı mı?"""
        self._frame_count += 1
        return self._frame_count % self._detect_every_n == 0 or self._cached_faces is None

    def update(self, faces):
        """Detection sonuçlarını cache'e yaz."""
        self._cached_faces = faces
        self._last_detect_ts = time.monotonic()
        self._cache_misses += 1
        if faces and len(faces) > 0:
            bbox = faces[0].bbox.astype(int)  # [x1, y1, x2, y2]
            self._cached_bbox = bbox
        else:
            self._cached_bbox = None

    def get_cached(self):
        """Önbellekteki faces'i döndür."""
        self._cache_hits += 1
        return self._cached_faces

    @property
    def hit_ratio(self) -> float:
        total = self._cache_hits + self._cache_misses
        return self._cache_hits / total if total > 0 else 0.0

    def get_stats(self) -> dict:
        return {
            "cache_hits":   self._cache_hits,
            "cache_misses": self._cache_misses,
            "hit_ratio":    f"{self.hit_ratio:.1%}",
        }


# ---------------------------------------------------------------------------
# Adaptif Frame Dropper
# ---------------------------------------------------------------------------

class AdaptiveFrameDropper:
    """
    İşleme süresine göre dinamik kare atlama.

    Strateji:
      - Son N karenin işleme süresinin hareketli ortalamasını hesapla
      - Ortalama > hedef_süre ise skip_factor'ü artır (daha çok kare atla)
      - Ortalama < hedef_süre ise skip_factor'ü azalt (daha az kare atla)
      - skip_factor her zaman [1, max_skip] aralığında kalır

    Örnek:
      GPU FPS 15 hedef → hedef_süre = 1/15 = 66ms
      İşleme 100ms → skip_factor 2'ye çıkar (her 2 karede 1 işle)
      İşleme 50ms  → skip_factor 1'e düşer (her kareyi işle)
    """

    def __init__(self, target_fps: float = 15.0, max_skip: int = 4, window_size: int = 10):
        self._target_ms   = 1000.0 / target_fps  # ms cinsinden hedef
        self._max_skip    = max_skip
        self._window_size = window_size
        self._times: list[float] = []             # Son N işleme süresi (ms)
        self._skip_factor = 1
        self._frame_count = 0

    def record_processing_time(self, elapsed_ms: float):
        """Bir karenin işleme süresini kaydet."""
        self._times.append(elapsed_ms)
        if len(self._times) > self._window_size:
            self._times.pop(0)
        self._adapt()

    def _adapt(self):
        """Hareketli ortalamaya göre skip_factor'ü güncelle."""
        if len(self._times) < 3:
            return
        avg = sum(self._times) / len(self._times)
        if avg > self._target_ms * 1.3:
            # Hedefin %30 üzerinde → skip artır
            self._skip_factor = min(self._skip_factor + 1, self._max_skip)
        elif avg < self._target_ms * 0.7 and self._skip_factor > 1:
            # Hedefin %30 altında ve skip > 1 → skip azalt
            self._skip_factor -= 1

    def should_process(self) -> bool:
        """Bu kare işlenmeli mi?"""
        self._frame_count += 1
        return self._frame_count % self._skip_factor == 0

    @property
    def skip_factor(self) -> int:
        return self._skip_factor

    @property
    def avg_processing_ms(self) -> float:
        return sum(self._times) / len(self._times) if self._times else 0.0


# ---------------------------------------------------------------------------
# DeepFake VideoTransformTrack (v2)
# ---------------------------------------------------------------------------

class DeepFakeVideoTrack(MediaStreamTrack):
    """
    Gelen video akışını (tarayıcı kamerası) gerçek zamanlı olarak değiştirir.

    v2 artırımları:
      - FaceBBoxCache ile algılama yükü ~60-70% azaltıldı
      - AdaptiveFrameDropper ile GPU aşırı yüklendiğinde kare atlanır
      - İstatistik loglama (her 30 saniye)

    aiortc mimarisi:
        Tarayıcı  ──WebRTC──►  DeepFakeVideoTrack.recv()
                                        │
                                        ▼
                             FaceSwapper.process_frame_raw_cached(img)
                                        │
                                        ▼
        Tarayıcı  ◄──WebRTC──  işlenmiş VideoFrame
    """

    kind = "video"

    def __init__(self, track: MediaStreamTrack, face_model: str = "face1"):
        super().__init__()
        self._track      = track
        self._face_model = face_model
        self._swapper    = get_face_swapper()
        self._last_processed: Optional[np.ndarray] = None

        # v2 optimizasyon bileşenleri
        self._bbox_cache   = FaceBBoxCache(detect_every_n=3, bbox_expand_ratio=0.15)
        self._frame_dropper = AdaptiveFrameDropper(target_fps=15.0, max_skip=4)

        # İstatistik loglama
        self._stats_frame_count = 0
        self._stats_start_time  = time.monotonic()

        # Aktif modeli ayarla
        self._swapper.select_model(face_model)
        logger.info(f"DeepFakeVideoTrack v2 oluşturuldu. face_model={face_model}")

    def set_face_model(self, model_id: str):
        if self._swapper.select_model(model_id):
            self._face_model = model_id
            logger.info(f"Face model değiştirildi: {model_id}")

    async def recv(self) -> av.VideoFrame:
        """
        aiortc her yeni kare için bu metodu çağırır.
        Gecikmeyi (latency) önlemek için AdaptiveFrameDropper kullanılarak
        GPU aşırı yüklendiğinde bazı karelerin işlenmesi atlanır.
        """
        frame: av.VideoFrame = await self._track.recv()
        self._stats_frame_count += 1

        # Eğer adaptif dropper bu kareyi atlamamız gerektiğini söylüyorsa,
        # gecikme (latency) oluşturmamak için GPU'yu es geç ve son kareyi ver.
        if not self._frame_dropper.should_process():
            if self._last_processed is not None:
                return ndarray_to_videoframe(self._last_processed, frame.pts, frame.time_base)
            return frame

        img = videoframe_to_ndarray(frame)
        processed = await asyncio.get_event_loop().run_in_executor(
            None,
            self._process_with_cache,
            img,
        )
        self._last_processed = processed

        # Periyodik istatistik logu (her ~30sn)
        elapsed = time.monotonic() - self._stats_start_time
        if elapsed >= 30.0:
            self._log_stats(elapsed)
            self._stats_frame_count = 0
            self._stats_start_time = time.monotonic()

        return ndarray_to_videoframe(processed, frame.pts, frame.time_base)

    def _process_with_cache(self, img: np.ndarray) -> np.ndarray:
        """
        Face-caching + adaptif frame-dropping ile optimize edilmiş işleme.
        FaceBBoxCache sayesinde her karede detection çalıştırmaz.
        """
        start = time.perf_counter()

        try:
            if self._swapper.app is None or self._swapper.swapper is None or self._swapper.source_face is None:
                return img

            # ── Face Detection (cached) ──
            if self._bbox_cache.should_detect():
                # Tam detection çalıştır
                faces = self._swapper.app.get(img)
                self._bbox_cache.update(faces)
            else:
                # Cache'ten al — detection atla
                faces = self._bbox_cache.get_cached()

            # ── Face Swap ──
            if faces and len(faces) > 0:
                img = self._swapper.swapper.get(
                    img, faces[0], self._swapper.source_face, paste_back=True
                )

            # ── Filigran ──
            cv2.putText(
                img, "AI GENERATED - DEEPFAKE", (15, 30),
                cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2,
            )

        except Exception as e:
            logger.error(f"Frame işleme hatası: {e}")

        elapsed_ms = (time.perf_counter() - start) * 1000
        self._frame_dropper.record_processing_time(elapsed_ms)

        return img

    def _log_stats(self, elapsed: float):
        """Periyodik performans logu."""
        avg_fps = self._stats_frame_count / elapsed if elapsed > 0 else 0
        cache_stats = self._bbox_cache.get_stats()
        logger.info(
            f"[Stats] FPS: {avg_fps:.1f} | "
            f"Skip: {self._frame_dropper.skip_factor}x | "
            f"Avg process: {self._frame_dropper.avg_processing_ms:.1f}ms | "
            f"Cache hit: {cache_stats['hit_ratio']} | "
            f"face_model: {self._face_model}"
        )
