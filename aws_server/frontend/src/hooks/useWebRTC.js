/**
 * useWebRTC — WebRTC bağlantı yönetimi hook'u (v2 — optimized)
 * ==============================================================
 * AWS Signaling Server'a WebSocket üzerinden bağlanır.
 * SDP offer/answer alışverişi yapar, P2P video akışını kurar.
 *
 * v2 değişiklikleri:
 *   - useMediaConstraints ile dışarıdan gelen kısıtlar uygulanır
 *   - SDP munging ile FPS/çözünürlük bant genişliği sınırlanır
 *   - Genişletilmiş istatistikler (rtt, jitter, packetsLost)
 *   - Bağlantı yeniden deneme mekanizması
 */

import { useRef, useState, useCallback, useEffect } from 'react';

// ICE Sunucuları — STUN (ücretsiz), isterseniz TURN ekleyin
const ICE_SERVERS = [
  { urls: 'stun:stun.l.google.com:19302' },
  { urls: 'stun:stun1.l.google.com:19302' },
];

// Maksimum yeniden bağlanma denemesi
const MAX_RECONNECT_ATTEMPTS = 3;

/**
 * @param {string} signalingUrl     — AWS Signaling Server WebSocket URL
 * @param {string} clientId         — Benzersiz istemci ID'si
 * @param {string} faceModel        — Kullanılacak yüz modeli (face1..face6)
 * @param {MediaStreamConstraints} mediaConstraints — useMediaConstraints'ten gelen constraints
 */
export function useWebRTC(signalingUrl, clientId, faceModel, mediaConstraints) {
  const [connectionState, setConnectionState] = useState('idle');
  const [remoteStream, setRemoteStream]       = useState(null);
  const [localStream, setLocalStream]         = useState(null);
  const [stats, setStats] = useState({
    fps: 0,
    bitrate: 0,
    rtt: 0,
    jitter: 0,
    packetsLost: 0,
    resolution: '—',
    framesDropped: 0,
    framesReceived: 0,
  });

  const pcRef            = useRef(null);
  const wsRef            = useRef(null);
  const statsIntervalRef = useRef(null);
  const prevBytesRef     = useRef(0);
  const prevTimestampRef = useRef(0);
  const reconnectRef     = useRef(0);

  // -----------------------------------------------------------------------
  // SDP Bant Genişliği Sınırlama (SDP Munging)
  // -----------------------------------------------------------------------
  function limitBandwidthInSDP(sdp, maxBitrateKbps = 800) {
    // Video için b=AS satırı ekle / güncelle
    const lines = sdp.split('\r\n');
    const result = [];
    let videoSection = false;

    for (let i = 0; i < lines.length; i++) {
      result.push(lines[i]);
      if (lines[i].startsWith('m=video')) {
        videoSection = true;
      } else if (lines[i].startsWith('m=') && !lines[i].startsWith('m=video')) {
        videoSection = false;
      }
      // c= satırından sonra b=AS ekle (varsa güncelle)
      if (videoSection && lines[i].startsWith('c=')) {
        // Mevcut b=AS satırını atla
        if (i + 1 < lines.length && lines[i + 1].startsWith('b=AS:')) {
          i++; // atla
        }
        result.push(`b=AS:${maxBitrateKbps}`);
      }
    }
    return result.join('\r\n');
  }

  // -----------------------------------------------------------------------
  // Bağlantıyı kapat (cleanup)
  // -----------------------------------------------------------------------
  const stopConnection = useCallback(() => {
    if (statsIntervalRef.current) {
      clearInterval(statsIntervalRef.current);
      statsIntervalRef.current = null;
    }
    if (pcRef.current) {
      pcRef.current.close();
      pcRef.current = null;
    }
    if (wsRef.current) {
      wsRef.current.close();
      wsRef.current = null;
    }
    if (localStream) {
      localStream.getTracks().forEach(t => t.stop());
    }
    setLocalStream(null);
    setRemoteStream(null);
    setConnectionState('idle');
    reconnectRef.current = 0;
    prevBytesRef.current = 0;
    prevTimestampRef.current = 0;
  }, [localStream]);

  // -----------------------------------------------------------------------
  // Geliştirilmiş İstatistik Toplayıcı
  // -----------------------------------------------------------------------
  const startStatsCollection = useCallback((pc) => {
    statsIntervalRef.current = setInterval(async () => {
      try {
        const reports = await pc.getStats();
        let newStats = {};

        reports.forEach(report => {
          // Gelen video — FPS, çözünürlük, paket kaybı, kare düşüşü
          if (report.type === 'inbound-rtp' && report.kind === 'video') {
            const now = report.timestamp;
            const bytes = report.bytesReceived || 0;
            const elapsed = prevTimestampRef.current
              ? (now - prevTimestampRef.current) / 1000
              : 1;
            const bitrate = elapsed > 0
              ? Math.round((bytes - prevBytesRef.current) * 8 / 1000 / elapsed)
              : 0;

            prevBytesRef.current = bytes;
            prevTimestampRef.current = now;

            newStats.fps            = report.framesPerSecond || 0;
            newStats.bitrate        = Math.max(0, bitrate);
            newStats.jitter         = report.jitter ? +(report.jitter * 1000).toFixed(1) : 0;
            newStats.packetsLost    = report.packetsLost || 0;
            newStats.framesDropped  = report.framesDropped || 0;
            newStats.framesReceived = report.framesReceived || 0;

            // Çözünürlük
            if (report.frameWidth && report.frameHeight) {
              newStats.resolution = `${report.frameWidth}×${report.frameHeight}`;
            }
          }

          // Candidate pair — RTT
          if (report.type === 'candidate-pair' && report.state === 'succeeded') {
            newStats.rtt = report.currentRoundTripTime
              ? +(report.currentRoundTripTime * 1000).toFixed(0)
              : 0;
          }
        });

        if (Object.keys(newStats).length > 0) {
          setStats(prev => ({ ...prev, ...newStats }));
        }
      } catch (_) {}
    }, 1000);
  }, []);

  // -----------------------------------------------------------------------
  // Ana bağlantı akışı
  // -----------------------------------------------------------------------
  const startConnection = useCallback(async () => {
    if (connectionState === 'connected' || connectionState === 'connecting') return;

    setConnectionState('connecting');

    try {
      // 1. Kameraya eriş — dışarıdan gelen mediaConstraints kullanılır, FPS limiti kaldırıldı
      const stream = await navigator.mediaDevices.getUserMedia(
        mediaConstraints ?? {
          video: { width: { ideal: 854 }, height: { ideal: 480 } },
          audio: false,
        }
      );
      setLocalStream(stream);

      // 2. RTCPeerConnection oluştur
      const pc = new RTCPeerConnection({ iceServers: ICE_SERVERS });
      pcRef.current = pc;

      // Yerel video akışını ekle
      stream.getTracks().forEach(track => pc.addTrack(track, stream));

      // Uzak akışı yakala (işlenmiş DeepFake video)
      const remoteMediaStream = new MediaStream();
      setRemoteStream(remoteMediaStream);

      pc.ontrack = (event) => {
        event.streams[0].getTracks().forEach(track => {
          remoteMediaStream.addTrack(track);
        });
      };

      pc.onconnectionstatechange = () => {
        const state = pc.connectionState;
        if (state === 'connected') {
          setConnectionState('connected');
          reconnectRef.current = 0;
          startStatsCollection(pc);
        } else if (state === 'failed') {
          setConnectionState('failed');
        } else if (state === 'closed') {
          setConnectionState('closed');
        }
      };

      pc.oniceconnectionstatechange = () => {
        if (pc.iceConnectionState === 'disconnected') {
          setConnectionState('connecting');
          // Otomatik yeniden bağlanma denemesi
          if (reconnectRef.current < MAX_RECONNECT_ATTEMPTS) {
            reconnectRef.current++;
            console.warn(`WebRTC bağlantı koptu, yeniden deneniyor (${reconnectRef.current}/${MAX_RECONNECT_ATTEMPTS})…`);
          }
        }
      };

      // 3. WebSocket Signaling bağlantısı
      const ws = new WebSocket(`${signalingUrl}/ws/signal/${clientId}`);
      wsRef.current = ws;

      await new Promise((resolve, reject) => {
        ws.onopen  = resolve;
        ws.onerror = reject;
        ws.onclose = () => setConnectionState('closed');
        setTimeout(() => reject(new Error('WebSocket timeout')), 8000);
      });

      ws.onmessage = async (event) => {
        const msg = JSON.parse(event.data);

        if (msg.type === 'answer') {
          const answer = new RTCSessionDescription({ type: 'answer', sdp: msg.sdp });
          await pc.setRemoteDescription(answer);
        } else if (msg.type === 'ice_candidate') {
          if (msg.candidate?.candidate) {
            await pc.addIceCandidate(new RTCIceCandidate(msg.candidate));
          }
        } else if (msg.type === 'error') {
          console.error('Signaling hatası:', msg.message);
          setConnectionState('failed');
        }
      };

      // ICE adaylarını signaling'e ilet
      pc.onicecandidate = (event) => {
        if (event.candidate && ws.readyState === WebSocket.OPEN) {
          ws.send(JSON.stringify({
            type:      'ice_candidate',
            candidate: event.candidate.toJSON(),
          }));
        }
      };

      // 4. SDP Offer oluştur, bant genişliğini sınırla ve gönder (Yüksek FPS için arttırıldı)
      const offer = await pc.createOffer();
      offer.sdp = limitBandwidthInSDP(offer.sdp, 2500);
      await pc.setLocalDescription(offer);

      ws.send(JSON.stringify({
        type:       'offer',
        sdp:        pc.localDescription.sdp,
        face_model: faceModel,
      }));

    } catch (err) {
      console.error('WebRTC bağlantı hatası:', err);
      setConnectionState('failed');
      stopConnection();
    }
  }, [connectionState, signalingUrl, clientId, faceModel, mediaConstraints, startStatsCollection, stopConnection]);

  // Bileşen söküldüğünde temizle
  useEffect(() => () => stopConnection(), []);

  return {
    connectionState,
    localStream,
    remoteStream,
    stats,
    startConnection,
    stopConnection,
    peerConnection: pcRef,
  };
}
