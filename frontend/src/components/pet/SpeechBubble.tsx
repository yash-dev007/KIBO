import { motion } from "framer-motion";

type SpeechBubbleProps = {
  text: string;
};

export function SpeechBubble({ text }: SpeechBubbleProps) {
  return (
    <motion.div
      className="mb-2 max-w-52 rounded border border-kibo-accent/20 bg-black/85 px-3 py-2 shadow-[0_0_16px_rgba(125,222,106,0.08)] backdrop-blur"
      initial={{ opacity: 0, y: 6, scale: 0.97 }}
      animate={{ opacity: 1, y: 0, scale: 1 }}
      exit={{ opacity: 0, y: 6 }}
    >
      <p className="mb-0.5 font-mono text-[9px] tracking-[0.25em] text-kibo-accent/50 uppercase">◈ kibo</p>
      <p className="text-xs leading-snug text-kibo-text">{text}</p>
    </motion.div>
  );
}
