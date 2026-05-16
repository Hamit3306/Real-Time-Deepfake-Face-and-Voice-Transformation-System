/**
 * VoiceCloneModule (Stub)
 * ========================
 * Gelecekte gerçek zamanlı ses klonlama entegrasyonu için hazır slot.
 * Event bus üzerinden video pipeline'dan izole çalışır.
 *
 * Uygulama planı:
 *   1. WebRTC audio track'ini yakala
 *   2. AudioWorklet ile sesi GPU Worker'a gönder
 *   3. GPU'daki RVC/SoVITS modelinden dönüştürülmüş sesi al
 *   4. Dönüştürülmüş audio track'i WebRTC'ye geri ekle
 */

export default class VoiceCloneModule {
  constructor(eventBus) {
    this.eventBus = eventBus;
    this.active = false;
    this._audioContext = null;

    // Event bus'tan gelen komutları dinle
    this.eventBus.on('module:voiceClone', (data) => this._onCommand(data));
    console.log('[VoiceCloneModule] Stub yüklendi — implementasyon bekleniyor.');
  }

  _onCommand(data) {
    if (data?.action === 'start') this.start(data);
    if (data?.action === 'stop')  this.stop();
  }

  async start({ audioStream } = {}) {
    if (this.active) return;
    this.active = true;

    // TODO: AudioWorklet ile ses yakalama
    // this._audioContext = new AudioContext({ sampleRate: 16000 });
    // const source = this._audioContext.createMediaStreamSource(audioStream);
    // ...

    console.log('[VoiceCloneModule] Başlatıldı (stub).');
  }

  stop() {
    this.active = false;
    if (this._audioContext) {
      this._audioContext.close();
      this._audioContext = null;
    }
    console.log('[VoiceCloneModule] Durduruldu.');
  }

  destroy() {
    this.stop();
  }
}
