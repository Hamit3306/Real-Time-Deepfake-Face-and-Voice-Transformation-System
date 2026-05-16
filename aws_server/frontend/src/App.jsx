/**
 * DeepFace Live — Ana Uygulama Bileşeni (App.jsx) — v2 Optimized
 * ================================================================
 * WebRTC P2P videosu: Tarayıcı kamerası → AWS Signaling → GPU Worker → P2P DeepFake
 *
 * v2 eklemeleri:
 *   - Performans kontrol paneli (çözünürlük/FPS profili seçimi)
 *   - Genişletilmiş istatistikler (RTT, jitter, paket kaybı, kare düşüşü)
 *   - Asenkron modül paneli (ses klonlama / toplantı kaydı / ekran paylaşımı)
 */

import { useState, useCallback, useEffect } from 'react';
import { useWebRTC } from './hooks/useWebRTC';
import { useMediaConstraints, QUALITY_PRESETS } from './hooks/useMediaConstraints';
import { useAsyncModules } from './hooks/useAsyncModules';
import VideoTile from './components/VideoTile';
// === Meeting Simulation (FR-4) ===
import MeetingScenarioPanel from './components/MeetingScenarioPanel';
import ParticipantsPanel from './components/ParticipantsPanel';
// === / Meeting Simulation ===

// Mevcut yüz modelleri
const FACE_MODELS = [
  { id: 'face1', label: 'Avatar 1', emoji: '🧑' },
  { id: 'face2', label: 'Avatar 2', emoji: '👩' },
  { id: 'face3', label: 'Avatar 3', emoji: '🧔' },
  { id: 'face4', label: 'Avatar 4', emoji: '👱' },
  { id: 'face5', label: 'Avatar 5', emoji: '🧓' },
  { id: 'face6', label: 'Avatar 6', emoji: '👨‍🦰' },
];

// Bağlantı durumu -> Türkçe metin + dot class
const STATE_MAP = {
  idle: { text: 'Bağlantı bekleniyor', dotClass: 'status-dot--idle' },
  connecting: { text: 'Bağlanıyor…', dotClass: 'status-dot--connecting' },
  connected: { text: 'P2P Bağlandı — WebRTC', dotClass: 'status-dot--connected' },
  failed: { text: 'Bağlantı başarısız', dotClass: 'status-dot--error' },
  closed: { text: 'Bağlantı kapatıldı', dotClass: 'status-dot--idle' },
};

// Benzersiz istemci ID'si (her sayfa yüklemesinde yeni)
const CLIENT_ID = crypto.randomUUID?.() ?? `client-${Date.now()}`;

// AWS Signaling Server URL'si (env'den okunur, default localhost dev için)
const SIGNALING_URL = import.meta.env.VITE_SIGNALING_WS_URL ?? 'ws://localhost:8000';

export default function App() {
  const [faceModel, setFaceModel] = useState('face1');
  const [signalingUrl, setSignalingUrl] = useState(SIGNALING_URL);
  const [urlInput, setUrlInput] = useState(SIGNALING_URL);

  // ── Ses Simülasyonu Ayarları ──
  const [voiceModel, setVoiceModel] = useState('');
  const [customVoices, setCustomVoices] = useState([]);
  const [speakingRate, setSpeakingRate] = useState(1.0);
  const [pitchAdjustment, setPitchAdjustment] = useState(0);
  const [emotion, setEmotion] = useState('neutral');
  const [isLiveMic, setIsLiveMic] = useState(false);

  // ── Chat Ayarları ──
  const [chatInput, setChatInput] = useState('');
  const [chatHistory, setChatHistory] = useState([
    { type: 'system', text: 'System: Interaction initialized. Chat is secure.' }
  ]);

  // === Meeting Simulation (FR-4) state ===
  const [activeScenarioId, setActiveScenarioId] = useState(null);
  const [activeScenario, setActiveScenario] = useState(null);
  const [participants, setParticipants] = useState([]); // FR-4.6
  const [isRoundRobinRunning, setIsRoundRobinRunning] = useState(false);
  // === / Meeting Simulation ===

  // ── useMediaConstraints — Çözünürlük/FPS kısıtları ──
  const { preset, setPreset, constraints, applyToStream, profile } = useMediaConstraints();

  // ── useWebRTC — Ana WebRTC bağlantısı ──
  const {
    connectionState, localStream, remoteStream, stats,
    startConnection, stopConnection, peerConnection,
  } = useWebRTC(signalingUrl, CLIENT_ID, faceModel, constraints);

  // ── useAsyncModules — Yan modüller (ses klonlama, kayıt, ekran) ──
  const { modules, moduleRegistry, toggleModule, moduleEvent } = useAsyncModules();

  const stateInfo = STATE_MAP[connectionState] ?? STATE_MAP.idle;
  const isActive = connectionState === 'connected' || connectionState === 'connecting';

  useEffect(() => {
    // Sunucudan mevcut ses kayıtlarını çek
    fetch('http://localhost:8001/api/voices')
      .then(res => res.json())
      .then(data => {
        if (data.voices) {
          setCustomVoices(data.voices);
          if (data.voices.length > 0) {
            setVoiceModel(data.voices[0]);
          }
        }
      })
      .catch(err => console.error("Ses listesi alınamadı:", err));
  }, []);

  const handleConnect = () => {
    setSignalingUrl(urlInput.trim());
    startConnection();
  };

  // Kalite profili değiştiğinde, açık stream'e de hemen uygula
  const handlePresetChange = (newPreset) => {
    setPreset(newPreset);
    if (localStream) applyToStream(localStream);
  };

  // ===========================================================================
  // Meeting Simulation handlers (FR-4)
  // ===========================================================================

  // Senaryo değiştiğinde: state güncelle + opening line'ı otomatik söyle (kullanıcı talebi)
  const handleScenarioChange = async (scenarioId, scenarioObj) => {
    setActiveScenarioId(scenarioId);
    setActiveScenario(scenarioObj);

    if (!scenarioId || !scenarioObj) {
      setChatHistory(prev => [...prev, { type: 'system', text: '🎬 Senaryo: Serbest sohbet moduna geçildi.' }]);
      return;
    }

    setChatHistory(prev => [...prev, {
      type: 'system',
      text: `🎬 Senaryo değiştirildi: ${scenarioObj.label}`,
    }]);

    // Opening line'ı seslendir
    try {
      const res = await fetch('http://localhost:8001/api/scenario/opening', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          scenario_id: scenarioId,
          persona: voiceModel,
          rate: speakingRate,
          pitch: pitchAdjustment,
          emotion: emotion,
        }),
      });
      const data = await res.json();
      if (data.text) {
        setChatHistory(prev => [...prev, { type: 'ai', text: data.text }]);
      }
      if (data.audio_url) {
        try {
          const audio = new Audio(data.audio_url);
          audio.play().catch(() => { });
        } catch (_) { }
      }
    } catch (err) {
      console.error('Opening line hatası:', err);
      setChatHistory(prev => [...prev, {
        type: 'system',
        text: '⚠️ Senaryo açılışı seslendirilemedi (mevcut sohbet etkilenmez).',
      }]);
    }
  };

  // Senaryo modu aktifken sohbet gönderimi: /api/chat-scenario endpoint'ine yönlendir
  const sendScenarioChat = async (message, participantOverride = null) => {
    const personaToUse = participantOverride?.voiceModel ?? voiceModel;
    const participantId = participantOverride?.id ?? null;
    const participantName = participantOverride?.name ?? null;

    try {
      const response = await fetch('http://localhost:8001/api/chat-scenario', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          message,
          scenario_id: activeScenarioId,
          persona: personaToUse,
          rate: speakingRate,
          pitch: pitchAdjustment,
          emotion: emotion,
          participant_id: participantId,
        }),
      });
      if (!response.ok) throw new Error('API yanıt vermedi');
      const data = await response.json();

      const prefix = participantName ? `[${participantName}] ` : '';
      setChatHistory(prev => {
        const cleaned = prev.filter(p => p.text !== 'AI düşünüyor ve ses sentezleniyor...');
        return [...cleaned, { type: 'ai', text: prefix + (data.response || '') }];
      });

      if (data.audio_url) {
        await new Promise((resolve) => {
          try {
            const audio = new Audio(data.audio_url);
            audio.onended = resolve;
            audio.onerror = resolve;
            audio.play().catch(resolve);
          } catch (_) { resolve(); }
        });
      }
      return data;
    } catch (err) {
      console.error('sendScenarioChat hatası:', err);
      setChatHistory(prev => {
        const cleaned = prev.filter(p => p.text !== 'AI düşünüyor ve ses sentezleniyor...');
        return [...cleaned, { type: 'system', text: 'Hata: Senaryo API bağlantısı kurulamadı.' }];
      });
      return null;
    }
  };

  // FR-4.6: Katılımcı yönetimi
  const handleAddParticipant = (participant) => {
    setParticipants(prev => [...prev, participant]);
  };
  const handleRemoveParticipant = (id) => {
    setParticipants(prev => prev.filter(p => p.id !== id));
  };
  const handleUpdateParticipant = (id, updates) => {
    setParticipants(prev => prev.map(p => p.id === id ? { ...p, ...updates } : p));
  };

  // FR-4.6: Sırayla konuşturma (round-robin)
  const handleRunRoundRobin = async () => {
    if (!activeScenarioId) {
      alert('Sırayla konuşturmak için önce bir senaryo seçin.');
      return;
    }
    if (participants.length === 0) {
      alert('Önce en az bir katılımcı ekleyin.');
      return;
    }
    // Son kullanıcı mesajını bul
    const lastUserMsg = [...chatHistory].reverse().find(m => m.type === 'user');
    if (!lastUserMsg) {
      alert('Önce sohbet kutusuna bir mesaj yazın, sonra sırayla konuşturun.');
      return;
    }

    setIsRoundRobinRunning(true);
    setChatHistory(prev => [...prev, {
      type: 'system',
      text: `🔄 Round-robin başladı (${participants.length} katılımcı)...`,
    }]);

    for (const participant of participants) {
      setChatHistory(prev => [...prev, {
        type: 'system',
        text: `→ ${participant.name} konuşuyor...`,
      }]);
      // Yüz modelini değiştir (görsel olarak)
      setFaceModel(participant.faceModel);
      // Cevap üret + bekle
      await sendScenarioChat(lastUserMsg.text, participant);
    }

    setChatHistory(prev => [...prev, { type: 'system', text: '✅ Round-robin tamamlandı.' }]);
    setIsRoundRobinRunning(false);
  };

  // ===========================================================================
  // / Meeting Simulation handlers
  // ===========================================================================

  const handleSendChat = async () => {
    if (!chatInput.trim()) return;
    const msg = chatInput.trim();
    setChatHistory(prev => [...prev, { type: 'user', text: msg }]);
    setChatInput('');

    // === Meeting Simulation: Senaryo aktifse o akışa devret ===
    if (activeScenarioId) {
      setChatHistory(prev => [...prev, { type: 'system', text: 'AI düşünüyor ve ses sentezleniyor...' }]);
      await sendScenarioChat(msg);
      return;
    }
    // === / Meeting Simulation ===

    setChatHistory(prev => [...prev, { type: 'system', text: 'AI düşünüyor ve ses sentezleniyor...' }]);

    try {
      const response = await fetch('http://localhost:8001/api/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          message: msg,
          persona: voiceModel,
          rate: speakingRate,
          pitch: pitchAdjustment,
          emotion: emotion
        })
      });

      if (!response.ok) throw new Error('API yanıt vermedi');

      const data = await response.json();

      setChatHistory(prev => {
        const newHistory = prev.filter(p => p.text !== 'AI düşünüyor ve ses sentezleniyor...');
        return [...newHistory, { type: 'ai', text: data.response }];
      });

      if (data.audio_url) {
        setChatHistory(prev => [...prev, { type: 'system', text: '🎵 Ses oynatılıyor...' }]);
        const audio = new Audio(data.audio_url);
        audio.play().catch(e => console.error("Audio playback error:", e));
      } else if (data.error) {
        setChatHistory(prev => [...prev, { type: 'system', text: 'Ses hatası: ' + data.error }]);
      }
    } catch (err) {
      console.error(err);
      setChatHistory(prev => {
        const newHistory = prev.filter(p => p.text !== 'AI düşünüyor ve ses sentezleniyor...');
        return [...newHistory, { type: 'system', text: 'Hata: GPU Worker API bağlantısı kurulamadı.' }];
      });
    }
  };

  const handleMicClick = async () => {
    if (isLiveMic) return;
    setIsLiveMic(true);
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const mediaRecorder = new MediaRecorder(stream);
      const audioChunks = [];

      mediaRecorder.ondataavailable = event => {
        audioChunks.push(event.data);
      };

      mediaRecorder.onstop = async () => {
        const audioBlob = new Blob(audioChunks, { type: 'audio/webm' });
        const formData = new FormData();
        formData.append('file', audioBlob, 'custom_voice.webm');

        try {
          const res = await fetch('http://localhost:8001/api/upload-voice', {
            method: 'POST',
            body: formData
          });
          const data = await res.json();
          if (data.status === 'ok') {
            const newPersona = data.persona;
            setCustomVoices(prev => [...prev, newPersona]);
            setVoiceModel(newPersona);
            alert(`🎤 Sesiniz başarıyla klonlandı! (${newPersona})`);
          } else {
            alert("Ses yüklenirken bir hata oluştu: " + (data.message || data.detail || "Bilinmeyen hata"));
          }
        } catch (err) {
          console.error(err);
          alert("Ses yüklenemedi. API bağlantısını kontrol edin.");
        }
        setIsLiveMic(false);
        stream.getTracks().forEach(track => track.stop());
      };

      mediaRecorder.start();
      setTimeout(() => {
        if (mediaRecorder.state === 'recording') {
          mediaRecorder.stop();
        }
      }, 5000); // 5 seconds recording

    } catch (err) {
      console.error("Mikrofon hatası:", err);
      setIsLiveMic(false);
      alert("Mikrofon izni alınamadı.");
    }
  };

  return (
    <div className="app">
      {/* ── Header ── */}
      <header className="header">
        <div className="header__logo">
          <div className="header__logo-icon">🎭</div>
          <span>DeepFace Live</span>
        </div>
        <span className="header__badge">WebRTC · P2P · Optimized</span>
      </header>

      {/* ── Main ── */}
      <main className="main">

        <div className="left-column" style={{ display: 'flex', flexDirection: 'column', gap: '24px' }}>
          {/* ── Video Stage ── */}
          <section className="video-stage glass-card">
            <div className="video-stage__title">
              📡 Canlı Video Akışı
            </div>

            <div className="video-grid">
              <VideoTile
                stream={localStream}
                label={`Orijinal — ${profile.width}×${profile.height} @ ${profile.fps}fps`}
                placeholder="📷"
              />
              <VideoTile
                stream={remoteStream}
                label={activeScenario ? `🎬 ${activeScenario.label} — AI Katılımcı` : "DeepFake (GPU)"}
                isDeepfake
                placeholder="🎭"
              />
            </div>

            {/* Status Bar */}
            <div className="status-bar" role="status" aria-live="polite">
              <span className={`status-dot ${stateInfo.dotClass}`} />
              <span>{stateInfo.text}</span>
              {connectionState === 'connected' && (
                <span style={{ marginLeft: 'auto', color: 'var(--clr-text-muted)', fontVariantNumeric: 'tabular-nums' }}>
                  {stats.fps | 0} fps · {stats.bitrate} kbps · {stats.rtt}ms RTT
                </span>
              )}
            </div>
          </section>

          {/* ── Chat Stage ── */}
          <section className="chat-stage glass-card">
            <div className="chat-stage__title">
              💬 AI Sohbet & Senaryo
            </div>
            <div className="chat-history">
              {chatHistory.map((msg, i) => (
                <div key={i} className={`message ${msg.type}`}>{msg.text}</div>
              ))}
            </div>
            <div className="chat-input-area">
              <input
                type="text"
                placeholder="Mesajınızı yazın..."
                value={chatInput}
                onChange={e => setChatInput(e.target.value)}
                onKeyDown={e => e.key === 'Enter' && handleSendChat()}
              />
              <button className="btn btn--primary" onClick={handleSendChat} style={{ width: 'auto', padding: '0 24px' }}>Gönder</button>
            </div>
          </section>
        </div>

        {/* ── Sidebar ── */}
        <aside className="sidebar">

          {/* === Meeting Simulation: Senaryo Paneli (FR-4.2..4.5) === */}
          <MeetingScenarioPanel
            activeScenarioId={activeScenarioId}
            onScenarioChange={handleScenarioChange}
            onSamplePromptClick={(text) => setChatInput(text)}
            disabled={isRoundRobinRunning}
          />

          {/* === Meeting Simulation: Çoklu Katılımcı (FR-4.6) === */}
          <ParticipantsPanel
            faceModels={FACE_MODELS}
            voiceModels={customVoices}
            participants={participants}
            onAddParticipant={handleAddParticipant}
            onRemoveParticipant={handleRemoveParticipant}
            onUpdateParticipant={handleUpdateParticipant}
            onRunRoundRobin={handleRunRoundRobin}
            disabled={isRoundRobinRunning}
          />

          {/* Yüz Modeli Seçimi */}
          <div className="glass-card">
            <p className="sidebar__section-title">Yüz Modeli Seç</p>
            <div className="face-grid" role="radiogroup" aria-label="Yüz modeli seçimi">
              {FACE_MODELS.map(face => (
                <button
                  key={face.id}
                  id={`face-btn-${face.id}`}
                  className={`face-card${faceModel === face.id ? ' face-card--active' : ''}`}
                  onClick={() => setFaceModel(face.id)}
                  role="radio"
                  aria-checked={faceModel === face.id}
                  title={face.label}
                >
                  <span className="face-card__emoji">{face.emoji}</span>
                  <span>{face.label}</span>
                </button>
              ))}
            </div>
          </div>

          {/* ── Ses Simülasyonu Ayarları ── */}
          <div className="glass-card">
            <p className="sidebar__section-title">Ses Simülasyonu</p>

            <div className="input-group" style={{ marginBottom: 12 }}>
              <label htmlFor="voice-select">Ses Modeli</label>
              <select
                id="voice-select"
                className="select-input"
                value={voiceModel}
                onChange={e => setVoiceModel(e.target.value)}
              >
                {customVoices.length === 0 && <option value="" disabled>Kayıtlı ses yok</option>}
                {customVoices.map(voice => (
                  <option key={voice} value={voice}>🎤 {voice.replace('_', ' ').toUpperCase()}</option>
                ))}
              </select>
            </div>

            <div className="slider-group">
              <label>Konuşma Hızı <span className="slider-val">{speakingRate}x</span></label>
              <input
                type="range"
                min="0.5" max="2.0" step="0.1"
                value={speakingRate}
                onChange={e => setSpeakingRate(parseFloat(e.target.value))}
              />
            </div>

            <div className="slider-group">
              <label>Ses Tonu (Pitch) <span className="slider-val">{pitchAdjustment} st</span></label>
              <input
                type="range"
                min="-12" max="12" step="1"
                value={pitchAdjustment}
                onChange={e => setPitchAdjustment(parseInt(e.target.value))}
              />
            </div>

            <div className="input-group" style={{ marginBottom: 16 }}>
              <label htmlFor="emotion-select">Duygu Tonu</label>
              <select
                id="emotion-select"
                className="select-input"
                value={emotion}
                onChange={e => setEmotion(e.target.value)}
              >
                <option value="neutral">Nötr (Varsayılan)</option>
                <option value="happy">Mutlu & Enerjik</option>
                <option value="serious">Ciddi & Otoriter</option>
              </select>
            </div>

            <button
              id="mic-btn"
              className={`btn ${isLiveMic ? 'btn--danger' : 'btn--primary'}`}
              onClick={handleMicClick}
              style={{ width: '100%', padding: '10px' }}
            >
              🎤 {isLiveMic ? 'Dinleniyor... (Durdur)' : 'Canlı Mikrofonu Kullan'}
            </button>
            <p style={{ fontSize: '0.65rem', color: 'var(--clr-text-muted)', marginTop: '8px', textAlign: 'center' }}>
              Ses Klonlama için mikrofondan canlı ses kaydet.
            </p>
          </div>

          {/* ── Performans Ayarları ── */}
          <div className="glass-card">
            <p className="sidebar__section-title">⚡ Performans Ayarları</p>
            <div className="quality-grid" role="radiogroup" aria-label="Kalite profili seçimi">
              {Object.entries(QUALITY_PRESETS).map(([key, p]) => (
                <button
                  key={key}
                  id={`quality-btn-${key}`}
                  className={`quality-btn${preset === key ? ' quality-btn--active' : ''}`}
                  onClick={() => handlePresetChange(key)}
                  role="radio"
                  aria-checked={preset === key}
                >
                  <span className="quality-btn__label">{p.label}</span>
                  <span className="quality-btn__detail">{p.width}×{p.height}</span>
                </button>
              ))}
            </div>
          </div>

          {/* Bağlantı Ayarları */}
          <div className="glass-card">
            <p className="sidebar__section-title">Bağlantı Ayarları</p>

            <div className="input-group" style={{ marginBottom: 14 }}>
              <label htmlFor="signaling-url-input">Signaling Server (AWS)</label>
              <input
                id="signaling-url-input"
                type="text"
                value={urlInput}
                onChange={e => setUrlInput(e.target.value)}
                placeholder="wss://your-aws-domain:8000"
                disabled={isActive}
              />
            </div>

            {!isActive ? (
              <button
                id="btn-connect"
                className="btn btn--primary"
                onClick={handleConnect}
              >
                🚀 Bağlantıyı Başlat
              </button>
            ) : (
              <button
                id="btn-disconnect"
                className={`btn ${connectionState === 'connecting' ? 'btn--secondary' : 'btn--danger'}`}
                onClick={stopConnection}
              >
                {connectionState === 'connecting' ? '⏳ Bağlanıyor…' : '⏹ Bağlantıyı Kes'}
              </button>
            )}
          </div>

          {/* ── Asenkron Modüller ── */}
          <div className="glass-card">
            <p className="sidebar__section-title">🧩 Ek Modüller</p>
            <div className="module-list">
              {Object.entries(moduleRegistry).map(([key, reg]) => {
                const state = modules[key];
                return (
                  <button
                    key={key}
                    id={`module-btn-${key}`}
                    className={`module-btn${state.active ? ' module-btn--active' : ''}`}
                    onClick={() => toggleModule(key)}
                    disabled={state.loading}
                    title={reg.description}
                  >
                    <span className="module-btn__icon">{reg.label.split(' ')[0]}</span>
                    <span className="module-btn__text">
                      {reg.label.split(' ').slice(1).join(' ')}
                      {state.loading && ' ⏳'}
                    </span>
                    <span className={`module-btn__indicator${state.active ? ' module-btn__indicator--on' : ''}`} />
                  </button>
                );
              })}
            </div>
          </div>

          {/* Geliştirilmiş İstatistikler */}
          <div className="glass-card">
            <p className="sidebar__section-title">📊 Detaylı İstatistikler</p>
            <div>
              <div className="stat-row">
                <span className="stat-row__label">Protokol</span>
                <span className="stat-row__value stat-row__value--accent">WebRTC P2P</span>
              </div>
              <div className="stat-row">
                <span className="stat-row__label">Çözünürlük</span>
                <span className="stat-row__value">{stats.resolution}</span>
              </div>
              <div className="stat-row">
                <span className="stat-row__label">FPS</span>
                <span className={`stat-row__value ${connectionState === 'connected' ? 'stat-row__value--success' : ''}`}>
                  {connectionState === 'connected' ? `${stats.fps | 0}` : '—'}
                </span>
              </div>
              <div className="stat-row">
                <span className="stat-row__label">Bit Hızı</span>
                <span className="stat-row__value">
                  {connectionState === 'connected' ? `${stats.bitrate} kbps` : '—'}
                </span>
              </div>
              <div className="stat-row">
                <span className="stat-row__label">RTT (Gecikme)</span>
                <span className="stat-row__value">
                  {connectionState === 'connected' ? `${stats.rtt} ms` : '—'}
                </span>
              </div>
              <div className="stat-row">
                <span className="stat-row__label">Jitter</span>
                <span className="stat-row__value">
                  {connectionState === 'connected' ? `${stats.jitter} ms` : '—'}
                </span>
              </div>
              <div className="stat-row">
                <span className="stat-row__label">Paket Kaybı</span>
                <span className={`stat-row__value ${stats.packetsLost > 50 ? 'stat-row__value--danger' : ''}`}>
                  {connectionState === 'connected' ? stats.packetsLost : '—'}
                </span>
              </div>
              <div className="stat-row">
                <span className="stat-row__label">Kareler (alınan/düşen)</span>
                <span className="stat-row__value" style={{ fontSize: '0.75rem' }}>
                  {connectionState === 'connected'
                    ? `${stats.framesReceived} / ${stats.framesDropped}`
                    : '—'}
                </span>
              </div>
              <div className="stat-row">
                <span className="stat-row__label">Yüz Modeli</span>
                <span className="stat-row__value stat-row__value--accent">{faceModel}</span>
              </div>
              <div className="stat-row">
                <span className="stat-row__label">İstemci ID</span>
                <span className="stat-row__value" style={{ fontSize: '0.68rem', opacity: 0.6 }}>
                  {CLIENT_ID.slice(0, 12)}…
                </span>
              </div>
            </div>
          </div>

          {/* Mimari Bilgisi */}
          <div className="glass-card" style={{ fontSize: '0.75rem', color: 'var(--clr-text-muted)', lineHeight: 1.7 }}>
            <p className="sidebar__section-title">Mimari</p>
            <p>🌐 <strong style={{ color: 'var(--clr-text-primary)' }}>AWS t2.micro</strong><br />
              React UI + FastAPI Signaling<br />
              Video verisi geçmez.</p>
            <p style={{ marginTop: 8 }}>
              🖥️ <strong style={{ color: 'var(--clr-text-primary)' }}>Yerel GPU</strong><br />
              FastAPI + aiortc + CUDA<br />
              Face-Cache + Adaptif Skip<br />
              Ngrok ile dışarıya açıktır.
            </p>
          </div>
        </aside>
      </main>

      <footer className="footer">
        AI GENERATED — Bu sistem akademik amaçlıdır. Gerçek kişilere uygulanması yasaktır.
      </footer>
    </div>
  );
}
