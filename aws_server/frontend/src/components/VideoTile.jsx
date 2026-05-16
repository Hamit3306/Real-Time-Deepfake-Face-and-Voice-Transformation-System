import { useRef, useEffect } from 'react';

/**
 * VideoTile — video akışını bir <video> elementine bağlar.
 */
export default function VideoTile({ stream, label, isDeepfake = false, placeholder = '📷' }) {
  const videoRef = useRef(null);

  useEffect(() => {
    if (videoRef.current && stream) {
      videoRef.current.srcObject = stream;
    }
  }, [stream]);

  return (
    <div className={`video-tile${isDeepfake ? ' video-tile--deepfake' : ''}`}>
      {stream ? (
        <video
          ref={videoRef}
          autoPlay
          playsInline
          muted={!isDeepfake}
        />
      ) : (
        <div className="video-tile__placeholder">
          <span className="video-tile__placeholder-icon">{placeholder}</span>
          <span>Bağlantı bekleniyor…</span>
        </div>
      )}
      <span className="video-tile__label">{label}</span>
    </div>
  );
}
