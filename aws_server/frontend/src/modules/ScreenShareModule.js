/**
 * ScreenShareModule (Stub)
 * ==========================
 * getDisplayMedia ile ekran paylaşımını WebRTC'ye ekleme altyapısı.
 *
 * Uygulama planı:
 *   1. getDisplayMedia() ile ekran akışı al
 *   2. Mevcut WebRTC bağlantısına replaceTrack() ile ekle
 *   3. GPU Worker tarafında ekran akışına da deepfake uygula
 *   4. Paylaşım bitince kameraya geri dön
 */

export default class ScreenShareModule {
  constructor(eventBus) {
    this.eventBus = eventBus;
    this._screenStream = null;
    this.active = false;

    this.eventBus.on('module:screenShare', (data) => this._onCommand(data));
    console.log('[ScreenShareModule] Stub yüklendi.');
  }

  _onCommand(data) {
    if (data?.action === 'start') this.start(data);
    if (data?.action === 'stop')  this.stop();
  }

  async start({ pcRef } = {}) {
    if (this.active) return;

    try {
      this._screenStream = await navigator.mediaDevices.getDisplayMedia({
        video: { width: { ideal: 1280 }, height: { ideal: 720 }, frameRate: { max: 15 } },
        audio: false,
      });
      this.active = true;

      // TODO: pcRef ile mevcut senderTrack'i replaceTrack() ile değiştir
      // const sender = pcRef.getSenders().find(s => s.track?.kind === 'video');
      // sender.replaceTrack(this._screenStream.getVideoTracks()[0]);

      // Kullanıcı tarayıcıdan paylaşımı durdurursa
      this._screenStream.getVideoTracks()[0].onended = () => this.stop();

      console.log('[ScreenShareModule] Ekran paylaşımı başlatıldı (stub).');
    } catch (err) {
      console.warn('[ScreenShareModule] Ekran paylaşımı başlatılamadı:', err);
      this.active = false;
    }
  }

  stop() {
    if (this._screenStream) {
      this._screenStream.getTracks().forEach(t => t.stop());
      this._screenStream = null;
    }
    this.active = false;

    // TODO: Kamera track'ine geri dön
    console.log('[ScreenShareModule] Ekran paylaşımı durduruldu.');
  }

  destroy() {
    this.stop();
  }
}
