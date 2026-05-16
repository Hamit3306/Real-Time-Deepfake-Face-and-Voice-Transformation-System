/**
 * MeetingRecordModule (Stub)
 * ===========================
 * Toplantı/oturum kaydı — MediaRecorder API ile tarayıcıda yerel kayıt.
 * Ana video pipeline'ını ETKİLEMEZ — ayrı bir MediaRecorder thread'inde çalışır.
 *
 * Uygulama planı:
 *   1. remoteStream'i (DeepFake çıktısı) MediaRecorder'a bağla
 *   2. Blob parçalarını biriktir (requestIdleCallback ile)
 *   3. Kaydı bitirince .webm dosyasını indirme olarak sun
 */

export default class MeetingRecordModule {
  constructor(eventBus) {
    this.eventBus = eventBus;
    this._recorder = null;
    this._chunks = [];
    this.recording = false;

    this.eventBus.on('module:meetingRecord', (data) => this._onCommand(data));
    console.log('[MeetingRecordModule] Stub yüklendi.');
  }

  _onCommand(data) {
    if (data?.action === 'start') this.start(data.stream);
    if (data?.action === 'stop')  this.stop();
  }

  start(stream) {
    if (this.recording || !stream) return;

    this._chunks = [];
    try {
      this._recorder = new MediaRecorder(stream, {
        mimeType: 'video/webm;codecs=vp9',
        videoBitsPerSecond: 1_500_000,
      });
    } catch {
      // VP9 desteklenmiyorsa fallback
      this._recorder = new MediaRecorder(stream);
    }

    this._recorder.ondataavailable = (e) => {
      if (e.data.size > 0) this._chunks.push(e.data);
    };

    this._recorder.onstop = () => this._saveRecording();
    this._recorder.start(1000); // Her saniye bir parça
    this.recording = true;
    console.log('[MeetingRecordModule] Kayıt başladı.');
  }

  stop() {
    if (!this.recording || !this._recorder) return;
    this._recorder.stop();
    this.recording = false;
    console.log('[MeetingRecordModule] Kayıt durduruluyor…');
  }

  _saveRecording() {
    if (this._chunks.length === 0) return;
    const blob = new Blob(this._chunks, { type: 'video/webm' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `deepface-recording-${new Date().toISOString().slice(0,19)}.webm`;
    a.click();
    URL.revokeObjectURL(url);
    this._chunks = [];
    console.log('[MeetingRecordModule] Kayıt indirildi.');
  }

  destroy() {
    this.stop();
  }
}
