// frontend/src/components/SignatureWatermark.tsx
import { motion, useReducedMotion } from 'framer-motion';
import { SignatureMark } from './SignatureMark';

interface SignatureWatermarkProps {
  className?: string;
}

/**
 * @description Faint, theme-aware signature watermark that reveals itself once
 * on mount with a slow left-to-right "signing" animation. Respects
 * prefers-reduced-motion by showing the signature instantly.
 */
export function SignatureWatermark({ className }: SignatureWatermarkProps) {
  const reduceMotion = useReducedMotion();

  if (reduceMotion) {
    return (
      <div className={`${className ?? ''} opacity-30 transition-colors duration-700`}>
        <SignatureMark className="w-44 h-auto text-gray-900 dark:text-white" />
      </div>
    );
  }

  return (
    <motion.div
      className={`${className ?? ''} transition-colors duration-700`}
      initial={{ clipPath: 'inset(0 100% 0 0)', opacity: 0 }}
      animate={{ clipPath: 'inset(0 0% 0 0)', opacity: 0.3 }}
      transition={{ duration: 1.4, ease: [0.22, 1, 0.36, 1], delay: 0.3 }}
    >
      <SignatureMark className="w-44 h-auto text-gray-900 dark:text-white" />
    </motion.div>
  );
}
