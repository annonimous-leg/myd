import { useEffect, useState } from 'react';
import { useSettingsStore } from '@/stores/useSettingsStore';

export function useResolvedTheme() {
  const theme = useSettingsStore(state => state.theme);
  const [systemDark, setSystemDark] = useState(() => window.matchMedia('(prefers-color-scheme: dark)').matches);
  useEffect(() => {
    const media = window.matchMedia('(prefers-color-scheme: dark)');
    const change = () => setSystemDark(media.matches);
    media.addEventListener('change', change);
    change();
    return () => media.removeEventListener('change', change);
  }, []);
  return theme === 'auto' ? (systemDark ? 'dark' : 'light') : theme;
}
