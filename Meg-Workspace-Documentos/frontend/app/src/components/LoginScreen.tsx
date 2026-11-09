/**
 * Copyright © 2026 Cristian Rodriguez
 * All rights reserved.
 * Unauthorized copying, modification, distribution, or use is prohibited
 * without prior written permission.
 */

import { useState } from 'react';
import { motion } from 'framer-motion';
import { User, Lock, Eye, EyeOff } from 'lucide-react';
import { useAuthStore } from '@/stores/useAuthStore';

export default function LoginScreen() {
  const login = useAuthStore(s => s.login);
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState('');

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    if (!username.trim()) {
      setError('El usuario es obligatorio');
      return;
    }
    if (!password.trim()) {
      setError('La contraseña es obligatoria');
      return;
    }
    setIsLoading(true);
    try {
      await login(username, password);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Usuario o contraseña incorrectos');
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50000 flex flex-col items-center overflow-y-auto py-6">
      {/* Background layers */}
      <div
        className="absolute inset-0 bg-cover bg-center"
        style={{ backgroundImage: 'url(/login-bg.jpg)' }}
      />
      <div
        className="absolute inset-0"
        style={{
          background: 'radial-gradient(ellipse at center, transparent 0%, rgba(3,3,5,0.4) 60%, rgba(3,3,5,0.85) 100%)',
        }}
      />

      {/* Content */}
      <div className="relative z-10 my-auto flex shrink-0 flex-col items-center max-w-[380px] w-full px-6">
        {/* Logo */}
        <motion.div
          initial={{ opacity: 0, scale: 0.8 }}
          animate={{ opacity: 1, scale: 1 }}
          transition={{ duration: 1.2, ease: [0.16, 1, 0.3, 1] as [number, number, number, number] }}
          className="mb-8"
        >
          <motion.div
            animate={{ opacity: [0.8, 1, 0.8], scale: [1, 1.02, 1] }}
            transition={{ duration: 4, repeat: Infinity, ease: 'easeInOut' }}
            className="w-20 h-20 rounded-full flex items-center justify-center"
            style={{
              background: 'radial-gradient(circle, rgba(201,168,76,0.2) 0%, transparent 70%)',
              boxShadow: '0 0 30px rgba(201,168,76,0.2)',
            }}
          >
            <svg viewBox="0 0 24 24" className="w-12 h-12" fill="#C9A84C">
              <path d="M12 2L2 7l10 5 10-5-10-5zM2 17l10 5 10-5M2 12l10 5 10-5" stroke="currentColor" strokeWidth="1.5" fill="none" />
            </svg>
          </motion.div>
        </motion.div>

        {/* Scripture Quote */}
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ delay: 0.5, duration: 1.5 }}
          className="text-center mb-8"
        >
          <p className="font-display text-[28px] text-[#E8E4DC] leading-tight tracking-wide">
            &ldquo;Ir&eacute; contigo y te dar&eacute; la victoria.&rdquo;
          </p>
          <p className="text-sm text-[#4D4A42] mt-3 font-ui">&mdash; &Eacute;xodo 33:14</p>
        </motion.div>

        {/* Login Form */}
        <motion.form
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 1.2, duration: 0.6, ease: [0.16, 1, 0.3, 1] as [number, number, number, number] }}
          onSubmit={handleSubmit}
          className="w-full glass rounded-xl p-8"
          style={{ boxShadow: 'var(--shadow-window)' }}
        >
          <div className="space-y-4">
            <div>
              <label className="block text-xs text-[#8A8578] mb-1.5">Correo electrónico</label>
              <div className="relative">
                <User className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-[#4D4A42]" />
                <input
                  type="email"
                  value={username}
                  onChange={(e) => { setUsername(e.target.value); setError(''); }}
                  placeholder="tu@correo.com"
                  className="w-full h-11 bg-[#0A0A0F] border border-[#2A2A3E] rounded-md pl-10 pr-3 text-sm text-[#E8E4DC] outline-hidden focus:border-[#C9A84C] transition-colors placeholder:text-[#4D4A42]"
                  autoFocus
                />
              </div>
            </div>

            <div>
              <label className="block text-xs text-[#8A8578] mb-1.5">Contrase&ntilde;a</label>
              <div className="relative">
                <Lock className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-[#4D4A42]" />
                <input
                  type={showPassword ? 'text' : 'password'}
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  placeholder="Ingresa tu contrase&ntilde;a"
                  className="w-full h-11 bg-[#0A0A0F] border border-[#2A2A3E] rounded-md pl-10 pr-10 text-sm text-[#E8E4DC] outline-hidden focus:border-[#C9A84C] transition-colors placeholder:text-[#4D4A42]"
                />
                <button
                  type="button"
                  onClick={() => setShowPassword(!showPassword)}
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-[#4D4A42] hover:text-[#8A8578] transition-colors"
                >
                  {showPassword ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                </button>
              </div>
            </div>

            {error && (
              <motion.p
                initial={{ opacity: 0, x: -4 }}
                animate={{ opacity: 1, x: [0, 4, -4, 4, 0] }}
                className="text-xs text-[#B84A4A]"
              >
                {error}
              </motion.p>
            )}

            <button
              type="submit"
              disabled={isLoading}
              className="w-full h-11 bg-[#C9A84C] text-[#030305] font-semibold text-sm rounded-md hover:bg-[#D4B85A] transition-all duration-150 hover:-translate-y-px active:scale-[0.98] disabled:opacity-60 disabled:cursor-not-allowed"
              style={{ boxShadow: 'var(--shadow-glow-gold)' }}
            >
              {isLoading ? (
                <span className="inline-block w-5 h-5 border-2 border-[#030305]/30 border-t-[#030305] rounded-full animate-spin" />
              ) : (
                'Entrar al Sistema'
              )}
            </button>
          </div>
        </motion.form>

        {/* Version */}
        <motion.p
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ delay: 2, duration: 1 }}
          className="mt-6 text-center text-xs text-[#4D4A42] font-mono"
        >
          Megalodon OS v3.1 &mdash; Build 2026.06
        </motion.p>
      </div>
    </div>
  );
}
