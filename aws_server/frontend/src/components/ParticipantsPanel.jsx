/**
 * ParticipantsPanel — Çoklu Katılımcı Paneli (FR-4.6)
 * =====================================================
 * Toplantıya birden fazla AI katılımcısı eklenir.
 * Her katılımcı kendi yüz modelini ve ses modelini kullanır.
 *
 * "Sırayla konuştur" butonu, mevcut sohbet kutusundaki son kullanıcı
 * mesajına her katılımcının kendi karakterinde cevap üretmesini sağlar
 * (round-robin).
 *
 * Mevcut tek katılımcılı akışa müdahale etmez; bu panel aktif kullanılmazsa
 * sistem aynen tek katılımcı modunda çalışır.
 */

import { useState } from 'react';

export default function ParticipantsPanel({
    faceModels,              // [{id, label, emoji}, ...]
    voiceModels,             // ['kayit_1', 'kayit_2', ...]
    participants,            // [{id, name, faceModel, voiceModel}, ...]
    onAddParticipant,
    onRemoveParticipant,
    onUpdateParticipant,
    onRunRoundRobin,         // sırayla konuşturma fonksiyonu
    disabled = false,
}) {
    const [newName, setNewName] = useState('');

    const handleAdd = () => {
        const name = newName.trim() || `Katılımcı ${participants.length + 1}`;
        onAddParticipant({
            id: `p_${Date.now()}_${Math.random().toString(36).slice(2, 7)}`,
            name,
            faceModel: faceModels[0]?.id ?? 'face1',
            voiceModel: voiceModels[0] ?? '',
        });
        setNewName('');
    };

    return (
        <div className="glass-card">
            <p className="sidebar__section-title">
                👥 Katılımcılar ({participants.length})
            </p>

            <p style={{
                fontSize: '0.7rem',
                color: 'var(--clr-text-muted)',
                marginBottom: 10,
                lineHeight: 1.5,
            }}>
                FR-4.6: Birden çok AI katılımcısı ekle. "Sırayla konuştur" ile her biri
                kendi karakterinde cevap üretir.
            </p>

            {/* Yeni katılımcı ekleme */}
            <div style={{ display: 'flex', gap: 6, marginBottom: 12 }}>
                <input
                    type="text"
                    value={newName}
                    onChange={e => setNewName(e.target.value)}
                    placeholder="İsim (opsiyonel)"
                    disabled={disabled}
                    onKeyDown={e => e.key === 'Enter' && handleAdd()}
                    style={{
                        flex: 1,
                        padding: '6px 10px',
                        fontSize: '0.75rem',
                        background: 'rgba(255,255,255,0.06)',
                        border: '1px solid rgba(255,255,255,0.1)',
                        borderRadius: 6,
                        color: 'var(--clr-text-primary)',
                    }}
                />
                <button
                    onClick={handleAdd}
                    disabled={disabled || voiceModels.length === 0}
                    className="btn btn--primary"
                    style={{ padding: '6px 12px', fontSize: '0.75rem', width: 'auto' }}
                >
                    ➕ Ekle
                </button>
            </div>

            {/* Katılımcı listesi */}
            {participants.length === 0 && (
                <p style={{
                    fontSize: '0.7rem',
                    color: 'var(--clr-text-muted)',
                    textAlign: 'center',
                    padding: '8px 0',
                }}>
                    Henüz katılımcı eklenmedi. Tek katılımcılı mod aktif.
                </p>
            )}

            <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                {participants.map((p, idx) => (
                    <div
                        key={p.id}
                        style={{
                            padding: '8px 10px',
                            background: 'rgba(255,255,255,0.04)',
                            borderRadius: 8,
                            border: '1px solid rgba(255,255,255,0.08)',
                        }}
                    >
                        <div style={{
                            display: 'flex',
                            justifyContent: 'space-between',
                            alignItems: 'center',
                            marginBottom: 6,
                        }}>
                            <strong style={{ fontSize: '0.78rem' }}>
                                #{idx + 1} {p.name}
                            </strong>
                            <button
                                onClick={() => onRemoveParticipant(p.id)}
                                disabled={disabled}
                                style={{
                                    background: 'transparent',
                                    border: 'none',
                                    color: '#ff8888',
                                    cursor: 'pointer',
                                    fontSize: '0.9rem',
                                }}
                                title="Sil"
                            >
                                ✕
                            </button>
                        </div>

                        <div style={{
                            display: 'grid',
                            gridTemplateColumns: '1fr 1fr',
                            gap: 6,
                        }}>
                            <select
                                value={p.faceModel}
                                onChange={e => onUpdateParticipant(p.id, { faceModel: e.target.value })}
                                disabled={disabled}
                                className="select-input"
                                style={{ fontSize: '0.7rem', padding: '4px 6px' }}
                            >
                                {faceModels.map(f => (
                                    <option key={f.id} value={f.id}>{f.emoji} {f.label}</option>
                                ))}
                            </select>

                            <select
                                value={p.voiceModel}
                                onChange={e => onUpdateParticipant(p.id, { voiceModel: e.target.value })}
                                disabled={disabled}
                                className="select-input"
                                style={{ fontSize: '0.7rem', padding: '4px 6px' }}
                            >
                                {voiceModels.length === 0 && <option value="">Ses yok</option>}
                                {voiceModels.map(v => (
                                    <option key={v} value={v}>🎤 {v}</option>
                                ))}
                            </select>
                        </div>
                    </div>
                ))}
            </div>

            {/* Sırayla konuştur */}
            {participants.length > 0 && (
                <button
                    onClick={onRunRoundRobin}
                    disabled={disabled}
                    className="btn btn--primary"
                    style={{ width: '100%', marginTop: 12, padding: 10 }}
                >
                    🔄 Sırayla Konuştur
                </button>
            )}
        </div>
    );
}
