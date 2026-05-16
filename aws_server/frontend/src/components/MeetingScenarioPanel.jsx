/**
 * MeetingScenarioPanel — Toplantı Senaryosu Seçim Paneli
 * ========================================================
 * FR-4.2..4.5: Önceden tanımlı 4 senaryo arasından seçim yapılır.
 *
 * Bu bileşen kendi içinde izoledir; props ile dışarıyla konuşur.
 * Mevcut sohbet/yüz/ses akışına müdahale etmez.
 */

import { useEffect, useState } from 'react';

const GPU_WORKER_URL = 'http://localhost:8001';

export default function MeetingScenarioPanel({
    activeScenarioId,        // şu an seçili senaryo (string | null)
    onScenarioChange,        // senaryo değişince çağrılır (id, scenarioObj) => void
    onSamplePromptClick,     // hızlı soru tıklanınca (text) => void
    disabled = false,
}) {
    const [scenarios, setScenarios] = useState([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState(null);

    useEffect(() => {
        let cancelled = false;
        (async () => {
            try {
                const res = await fetch(`${GPU_WORKER_URL}/api/scenarios`);
                const data = await res.json();
                if (cancelled) return;
                if (data.scenarios && data.scenarios.length > 0) {
                    setScenarios(data.scenarios);
                } else {
                    setError(data.error || 'Senaryo bulunamadı.');
                }
            } catch (err) {
                if (!cancelled) setError('Senaryo listesi yüklenemedi.');
            } finally {
                if (!cancelled) setLoading(false);
            }
        })();
        return () => { cancelled = true; };
    }, []);

    const activeScenario = scenarios.find(s => s.id === activeScenarioId);

    return (
        <div className="glass-card">
            <p className="sidebar__section-title">🎬 Toplantı Senaryosu</p>

            {loading && (
                <p style={{ fontSize: '0.75rem', color: 'var(--clr-text-muted)' }}>
                    Senaryolar yükleniyor...
                </p>
            )}

            {error && !loading && (
                <p style={{ fontSize: '0.7rem', color: '#ff8888' }}>
                    ⚠️ {error} (Senaryo özelliği kullanılamıyor, sohbet normal devam eder.)
                </p>
            )}

            {!loading && !error && (
                <>
                    <div className="face-grid" role="radiogroup" aria-label="Senaryo seçimi">
                        {/* "Yok" seçeneği — senaryo dışı normal sohbet */}
                        <button
                            className={`face-card${!activeScenarioId ? ' face-card--active' : ''}`}
                            onClick={() => onScenarioChange(null, null)}
                            disabled={disabled}
                            role="radio"
                            aria-checked={!activeScenarioId}
                            title="Senaryo dışı serbest sohbet"
                        >
                            <span className="face-card__emoji">💬</span>
                            <span>Serbest</span>
                        </button>

                        {scenarios.map(s => (
                            <button
                                key={s.id}
                                className={`face-card${activeScenarioId === s.id ? ' face-card--active' : ''}`}
                                onClick={() => onScenarioChange(s.id, s)}
                                disabled={disabled}
                                role="radio"
                                aria-checked={activeScenarioId === s.id}
                                title={s.description}
                            >
                                <span className="face-card__emoji">{s.emoji}</span>
                                <span>{s.label}</span>
                            </button>
                        ))}
                    </div>

                    {activeScenario && (
                        <div style={{
                            marginTop: 12,
                            padding: '10px 12px',
                            background: 'rgba(255,255,255,0.04)',
                            borderRadius: 8,
                            fontSize: '0.72rem',
                            color: 'var(--clr-text-muted)',
                            lineHeight: 1.55,
                        }}>
                            <strong style={{ color: 'var(--clr-text-primary)' }}>
                                {activeScenario.label}
                            </strong>
                            <br />
                            {activeScenario.description}
                        </div>
                    )}

                    {activeScenario && activeScenario.sample_prompts?.length > 0 && (
                        <div style={{ marginTop: 12 }}>
                            <p style={{
                                fontSize: '0.7rem',
                                color: 'var(--clr-text-muted)',
                                marginBottom: 6,
                            }}>
                                Hızlı sorular:
                            </p>
                            <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                                {activeScenario.sample_prompts.map((q, i) => (
                                    <button
                                        key={i}
                                        onClick={() => onSamplePromptClick?.(q)}
                                        disabled={disabled}
                                        style={{
                                            textAlign: 'left',
                                            padding: '6px 10px',
                                            fontSize: '0.72rem',
                                            background: 'rgba(255,255,255,0.05)',
                                            border: '1px solid rgba(255,255,255,0.08)',
                                            borderRadius: 6,
                                            color: 'var(--clr-text-primary)',
                                            cursor: disabled ? 'not-allowed' : 'pointer',
                                        }}
                                    >
                                        💡 {q}
                                    </button>
                                ))}
                            </div>
                        </div>
                    )}
                </>
            )}
        </div>
    );
}
