import { useLayoutEffect } from 'react';
import { useResolvedTheme } from '@/hooks/useResolvedTheme';
import { Moon, Sun } from 'lucide-react';
import { useSettingsStore } from '@/stores/useSettingsStore';

export function ThemeController() {
  const theme = useResolvedTheme();
  useLayoutEffect(() => {
    document.documentElement.dataset.theme = theme;
    document.documentElement.classList.toggle('dark', theme === 'dark');
    document.documentElement.style.colorScheme = theme;
  }, [theme]);
  return null;
}

export default function ThemeControl() {
  const theme = useResolvedTheme();
  const update = useSettingsStore(state => state.updateSetting);
  const dark = theme === 'dark';
  return <button type="button" className="shell-icon-button" aria-label={dark ? 'Activar modo claro' : 'Activar modo oscuro'}
    onClick={() => update('theme', dark ? 'light' : 'dark')} title={dark ? 'Modo claro' : 'Modo oscuro'}>
    {dark ? <Sun size={18} aria-hidden /> : <Moon size={18} aria-hidden />}
  </button>;
}
