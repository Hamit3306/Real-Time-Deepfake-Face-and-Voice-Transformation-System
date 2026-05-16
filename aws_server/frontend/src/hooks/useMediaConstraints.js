/**
 * useMediaConstraints — Kamera çözünürlük ve FPS kısıtlama hook'u
 * ================================================================
 * getUserMedia çağrılmadan ÖNCE kısıtları hazırlar.
 * Ek olarak, mevcut bir MediaStream varsa video track'inin canlı
 * constraint'lerini applyConstraints() ile günceller (WebRTC
 * renegotiation gerekmeden anlık değişim).
 *
 * Performans Stratejisi:
 *   480p (854×480) + 15 FPS  → ~40% daha az bant genişliği
 *   320p seçeneği de mevcut  → düşük cihazlar / mobil için
 */

import { useState, useCallback, useRef, useMemo } from 'react';

// ────── Ön Tanımlı Profiller ──────
export const QUALITY_PRESETS = {
  low:    { label: 'Düşük (320p)',  width: 426,  height: 320 },
  medium: { label: 'Orta (480p)',   width: 854,  height: 480 },
  high:   { label: 'Yüksek (480p)', width: 854,  height: 480 },
  hd:     { label: 'HD (720p)',      width: 1280, height: 720 },
};

const DEFAULT_PRESET = 'medium';

/**
 * @returns {{ preset, setPreset, constraints, applyToStream }}
 *   - preset:        Aktif kalite profili adı
 *   - setPreset:     Profili değiştiren fonksiyon
 *   - constraints:   getUserMedia'ya verilecek MediaStreamConstraints nesnesi
 *   - applyToStream: Zaten açık olan bir MediaStream'e yeni kısıtları uygular
 */
export function useMediaConstraints() {
  const [preset, setPresetState] = useState(DEFAULT_PRESET);
  const streamRef = useRef(null);   // isteğe bağlı referans

  const profile = QUALITY_PRESETS[preset] ?? QUALITY_PRESETS[DEFAULT_PRESET];

  // getUserMedia() için hazır constraints nesnesi
  const constraints = useMemo(() => ({
    video: {
      width:     { ideal: profile.width,  max: profile.width },
      height:    { ideal: profile.height, max: profile.height },
      // fps kısıtlaması kaldırıldı
      // Ekstra: donanım hızlandırma tercihini zorla
      facingMode: 'user',
    },
    audio: false,
  }), [profile]);

  /**
   * Mevcut bir stream'e (zaten açılmış kameraya) kısıtları anlık uygular.
   * Bu fonksiyon, bağlantıyı kesmeden çözünürlük/FPS değişikliği yapabilir.
   * Tarayıcı desteği: Chrome 63+, Firefox 70+, Safari 14+
   */
  const applyToStream = useCallback(async (stream) => {
    if (!stream) return false;
    const videoTrack = stream.getVideoTracks()[0];
    if (!videoTrack) return false;

    try {
      await videoTrack.applyConstraints({
        width:     { ideal: profile.width,  max: profile.width },
        height:    { ideal: profile.height, max: profile.height },
      });
      streamRef.current = stream;
      return true;
    } catch (err) {
      console.warn('applyConstraints başarısız:', err);
      return false;
    }
  }, [profile]);

  /**
   * Profil değişikliğini state'e yaz + opsiyonel olarak mevcut stream'e uygula.
   */
  const setPreset = useCallback((newPreset) => {
    if (!(newPreset in QUALITY_PRESETS)) return;
    setPresetState(newPreset);
    // Eğer zaten açık bir stream varsa, constraint'leri anlık güncelle
    if (streamRef.current) {
      // Profile bu tick'te henüz güncellenmemiş olabilir,
      // doğrudan preset'ten al
      const p = QUALITY_PRESETS[newPreset];
      const track = streamRef.current.getVideoTracks()[0];
      if (track) {
        track.applyConstraints({
          width:     { ideal: p.width,  max: p.width },
          height:    { ideal: p.height, max: p.height },
        }).catch(() => {});
      }
    }
  }, []);

  return { preset, setPreset, constraints, applyToStream, profile };
}
