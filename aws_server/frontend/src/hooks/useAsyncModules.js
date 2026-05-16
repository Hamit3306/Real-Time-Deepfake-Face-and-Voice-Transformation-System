/**
 * useAsyncModules — Performansı etkilemeden gelecek özellikleri çalıştımak için
 * ==============================================================================
 * ses klonlama, toplantı kaydı, ekran paylaşımı gibi yan görevleri
 * ana video pipeline'ından izole eder.
 *
 * Mimari:
 *   1. Her modül lazy-loaded (dynamik import) — başlangıçta yüklenmez.
 *   2. Her modül kendi Web Worker veya requestIdleCallback döngüsünde çalışır.
 *   3. Modüller arası iletişim basit bir EventTarget (event bus) ile sağlanır.
 *   4. Modüller etkinleştirilebilir/devre dışı bırakılabilir.
 *
 * Kullanım:
 *   const { modules, toggleModule, moduleEvent } = useAsyncModules();
 *   toggleModule('voiceClone');       // Ses klonlama modülünü başlat
 *   moduleEvent('voiceClone', data);  // Modüle veri gönder
 */

import { useState, useCallback, useRef, useEffect } from 'react';

// ────── Modül Tanımları ──────
// Her modülün factory'si lazy-loaded import döndürür.
// Gerçek implementasyonlar ileriki adımlarda oluşturulacak.
const MODULE_REGISTRY = {
  voiceClone: {
    label:       '🎤 Ses Klonlama',
    description: 'Gerçek zamanlı ses dönüştürme (WebRTC audio track)',
    factory:     () => import('../modules/VoiceCloneModule.js').catch(() => null),
    requiresAudio: true,
  },
  meetingRecord: {
    label:       '📹 Toplantı Kaydı',
    description: 'Oturumu MediaRecorder API ile yerel diske kaydet',
    factory:     () => import('../modules/MeetingRecordModule.js').catch(() => null),
    requiresAudio: false,
  },
  screenShare: {
    label:       '🖥️ Ekran Paylaşımı',
    description: `getDisplayMedia ile ekran akışını WebRTC'ye ekle`,
    factory:     () => import('../modules/ScreenShareModule.js').catch(() => null),
    requiresAudio: false,
  },
};

/**
 * Basit Event Bus — modüller arası ve modül↔UI arası iletişim.
 * performansı etkilememesi için senkron emit + mikrotask queue kullanır.
 */
function createEventBus() {
  const target = new EventTarget();
  return {
    on:   (name, fn) => { target.addEventListener(name, (e) => fn(e.detail)); },
    off:  (name, fn) => { target.removeEventListener(name, fn); },
    emit: (name, data) => {
      // requestIdleCallback ile, ana thread boşken ateşle
      const dispatch = () => target.dispatchEvent(new CustomEvent(name, { detail: data }));
      if (typeof requestIdleCallback === 'function') {
        requestIdleCallback(dispatch, { timeout: 50 });
      } else {
        setTimeout(dispatch, 0);
      }
    },
  };
}

export function useAsyncModules() {
  const busRef = useRef(createEventBus());

  // { modülAdı: { active: bool, instance: ModuleInstance | null, loading: bool } }
  const [modules, setModules] = useState(() => {
    const initial = {};
    for (const key of Object.keys(MODULE_REGISTRY)) {
      initial[key] = { active: false, instance: null, loading: false };
    }
    return initial;
  });

  /**
   * Modülü aç/kapa (toggle).
   */
  const toggleModule = useCallback(async (moduleKey) => {
    const reg = MODULE_REGISTRY[moduleKey];
    if (!reg) return;

    setModules(prev => {
      const current = prev[moduleKey];
      if (current.active) {
        // Kapat — instance'ı temizle
        if (current.instance?.destroy) current.instance.destroy();
        return { ...prev, [moduleKey]: { active: false, instance: null, loading: false } };
      }
      // Aç — loading durumuna geç
      return { ...prev, [moduleKey]: { ...current, loading: true } };
    });

    // Lazy-load
    const mod = await reg.factory();
    if (!mod || !mod.default) {
      // Modül henüz kodlanmadıysa stub olarak kalsın
      setModules(prev => ({
        ...prev,
        [moduleKey]: { active: true, instance: null, loading: false },
      }));
      return;
    }

    const instance = new mod.default(busRef.current);
    setModules(prev => ({
      ...prev,
      [moduleKey]: { active: true, instance, loading: false },
    }));
  }, []);

  /**
   * Belirli bir modüle event bus üzerinden mesaj gönder.
   */
  const moduleEvent = useCallback((moduleKey, data) => {
    busRef.current.emit(`module:${moduleKey}`, data);
  }, []);

  // Cleanup — bileşen unmount olduğunda tüm aktif modülleri kapat
  useEffect(() => {
    return () => {
      Object.values(modules).forEach(m => {
        if (m.instance?.destroy) m.instance.destroy();
      });
    };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return { modules, moduleRegistry: MODULE_REGISTRY, toggleModule, moduleEvent, eventBus: busRef.current };
}
