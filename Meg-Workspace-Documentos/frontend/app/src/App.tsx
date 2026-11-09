/**
 * Copyright © 2026 Cristian Rodriguez
 * All rights reserved.
 * Unauthorized copying, modification, distribution, or use is prohibited
 * without prior written permission.
 */

import { useEffect } from 'react';
import { AnimatePresence, motion } from 'framer-motion';
import { useAuthStore } from '@/stores/useAuthStore';
import LoginScreen from '@/components/LoginScreen';
import BootSequence from '@/components/BootSequence';
import CommandCenter from '@/components/CommandCenter';

export default function App() {
  const { isAuthenticated, isBootComplete, isCheckingSession, restoreSession } = useAuthStore();
  useEffect(() => { void restoreSession(); }, [restoreSession]);
  if (isCheckingSession) {
    return <div className="w-full h-full bg-[#030305] text-white flex items-center justify-center" role="status">Comprobando sesión…</div>;
  }

  return (
    <div className="w-full h-full overflow-hidden bg-[#030305]">
      <AnimatePresence mode="wait">
        {!isAuthenticated && (
          <motion.div
            key="login"
            exit={{ opacity: 0, scale: 0.98 }}
            transition={{ duration: 0.4 }}
            className="w-full h-full"
          >
            <LoginScreen />
          </motion.div>
        )}

        {isAuthenticated && !isBootComplete && (
          <motion.div
            key="boot"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.3 }}
            className="w-full h-full"
          >
            <BootSequence />
          </motion.div>
        )}

        {isAuthenticated && isBootComplete && (
          <motion.div
            key="command-center"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ duration: 0.8, delay: 0.2 }}
            className="w-full h-full"
          >
            <CommandCenter />
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
