import { useState, useRef, useEffect } from 'react';
import { motion } from 'motion/react';
import { Paperclip, Mic, Send, X } from 'lucide-react';
import { useVoiceBridge } from '@/hooks/useVoiceBridge';

interface ChatInputProps {
  onSend: (content: string, attachments?: Array<{ name: string; type: string; size: number; url?: string; data?: string }>) => void;
  reduceMotion: boolean;
}

export function ChatInput({ onSend, reduceMotion }: ChatInputProps) {
  const [input, setInput] = useState('');
  const [uploadedFiles, setUploadedFiles] = useState<Array<{ name: string; type: string; size: number; url?: string; data?: string }>>([]);
  const [isRecording, setIsRecording] = useState(false);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const { status: voiceStatus } = useVoiceBridge();

  useEffect(() => {
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto';
      textareaRef.current.style.height = `${Math.min(textareaRef.current.scrollHeight, 150)}px`;
    }
  }, [input]);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!input.trim() && uploadedFiles.length === 0) return;
    onSend(input.trim(), uploadedFiles.length > 0 ? uploadedFiles : undefined);
    setInput('');
    setUploadedFiles([]);
  };

  const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = e.target.files;
    if (!files) return;
    Array.from(files).forEach((file) => {
      const url = URL.createObjectURL(file);
      setUploadedFiles((prev) => [...prev, { name: file.name, type: file.type, size: file.size, url }]);
    });
    e.target.value = '';
  };

  const handleVoiceClick = () => {
    if (isRecording) {
      setIsRecording(false);
    } else if (voiceStatus === 'connected') {
      setIsRecording(true);
    }
  };

  return (
    <form className="floating-chat-input" onSubmit={handleSubmit}>
      {uploadedFiles.length > 0 && (
        <div className="floating-chat-attachments">
          {uploadedFiles.map((file, i) => (
            <span key={i} className="floating-chat-attachment">
              {file.name}
              <button type="button" onClick={() => setUploadedFiles((prev) => prev.filter((_, idx) => idx !== i))} aria-label="Remove attachment">
                <X className="w-3 h-3" />
              </button>
            </span>
          ))}
        </div>
      )}

      <div className="floating-chat-input-row">
        <button
          type="button"
          className="floating-chat-input-btn"
          onClick={() => fileInputRef.current?.click()}
          aria-label="Attach file"
          disabled={isRecording}
        >
          <Paperclip className="w-5 h-5" />
        </button>
        <input type="file" ref={fileInputRef} onChange={handleFileSelect} className="sr-only" multiple />

        <textarea
          ref={textareaRef}
          placeholder="Type a message..."
          value={input}
          onChange={(e) => setInput(e.target.value)}
          className="floating-chat-textarea"
          rows={1}
          disabled={isRecording}
          aria-label="Chat message"
        />

        <button
          type="button"
          className="floating-chat-input-btn"
          onClick={handleVoiceClick}
          aria-label={isRecording ? 'Stop voice recording' : 'Start voice recording'}
          disabled={voiceStatus !== 'connected'}
        >
          <Mic className={`w-5 h-5 ${isRecording ? 'text-red-500' : ''}`} />
        </button>

        <motion.button
          type="submit"
          className="floating-chat-send-btn"
          disabled={!input.trim() && uploadedFiles.length === 0}
          whileTap={{ scale: 0.9 }}
          aria-label="Send message"
        >
          <Send className="w-5 h-5" />
        </motion.button>
      </div>

      <p className="floating-chat-disclaimer">Build By Ashmin Dhungana</p>
    </form>
  );
}