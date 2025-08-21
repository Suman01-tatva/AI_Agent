import React, { useState, useRef, useEffect, useCallback } from "react";
import parse from "html-react-parser";

const Chatbot = () => {
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState("");
  const [recording, setRecording] = useState(false);
  const [showAttachMenu, setShowAttachMenu] = useState(false);
  const [language, setLanguage] = useState("en"); // 🌍 Selected language
  const chatRef = useRef();
  const mediaRecorderRef = useRef(null);
  const audioChunksRef = useRef([]);
  const silenceTimerRef = useRef(null);
  const [selectedImage, setSelectedImage] = useState(null);
  const fileInputRef = useRef(null);

  const SILENCE_TIMEOUT = 1500; // ms of silence before auto-stop

  const FlagIcon = ({ country, className = "w-5 h-5" }) => {
    const flags = {
      us: "🇺🇸",
      in: "🇮🇳",
    };

    return (
      <span
        className={`inline-flex items-center justify-center text-sm ${className}`}
      >
        {flags[country]}
      </span>
    );
  };

  const handleImageSelect = (e) => {
    const file = e.target.files[0];
    if (file) {
      setSelectedImage(file);
      setShowAttachMenu(false);
    }
  };

  const removeSelectedImage = () => {
    setSelectedImage(null);
  };

  // Scroll chat to bottom
  useEffect(() => {
    if (chatRef.current) {
      chatRef.current.scrollTop = chatRef.current.scrollHeight;
    }
  }, [messages]);

  const sendImage = async () => {
    if (!selectedImage) return;

    const imageMessage = {
      role: "user",
      parts: [{ text: input }, { image: URL.createObjectURL(selectedImage) }],
    };
    setMessages((prev) => [...prev, imageMessage]);
    setInput("");

    const formData = new FormData();
    formData.append("image", selectedImage);
    formData.append("prompt", input || "Describe this image");

    try {
      const res = await fetch("http://localhost:5000/image-chat", {
        method: "POST",
        body: formData,
      });

      const data = await res.json();
      if (data.error) {
        setMessages((prev) => [
          ...prev,
          { role: "model", parts: [{ text: `❌ ${data.error}` }] },
        ]);
      } else {
        const botMsg = { role: "model", parts: [{ text: data.response }] };
        setMessages((prev) => [...prev, botMsg]);
      }
    } catch (err) {
      setMessages((prev) => [
        ...prev,
        { role: "model", parts: [{ text: `⚠️ Error: ${err.message}` }] },
      ]);
    } finally {
      setSelectedImage(null);
    }
  };

  // 📤 Send message to chatbot + TTS
  const sendMessage = useCallback(
    async (customInput, speak = false) => {
      const messageToSend = customInput || input;
      if (!messageToSend.trim()) return;

      const newUserMessage = { role: "user", parts: [{ text: messageToSend }] };
      setMessages((prev) => [...prev, newUserMessage]);
      setInput("");

      try {
        // Step 1: Chatbot response
        const response = await fetch("http://localhost:5000/chat", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ message: messageToSend }),
        });

        const data = await response.json();
        if (data.error) {
          setMessages((prev) => [
            ...prev,
            { role: "model", parts: [{ text: `❌ ${data.error}` }] },
          ]);
          return;
        }

        const botReply = data.response;
        setMessages((prev) => [
          ...prev,
          { role: "model", parts: [{ text: botReply }] },
        ]);

        // // Step 2: Play bot reply via TTS
        // if (speak) {
        //   const ttsRes = await fetch("http://localhost:5000/tts", {
        //     method: "POST",
        //     headers: { "Content-Type": "application/json" },
        //     body: JSON.stringify({ text: botReply, language }), // send language for TTS
        //   });

        //   const ttsData = await ttsRes.json();
        //   if (ttsData.audio) {
        //     const audio = new Audio(`data:audio/mpeg;base64,${ttsData.audio}`);
        //     audio.play();
        //   } else {
        //     console.error("TTS error:", ttsData.error || "Unknown error");
        //   }
        // }
      } catch (err) {
        setMessages((prev) => [
          ...prev,
          { role: "model", parts: [{ text: `⚠️ Error: ${err.message}` }] },
        ]);
      }
    },
    [input, language]
  );

  // Handle STT sending
  const sendAudioForTranscription = async (audioBlob) => {
    const formData = new FormData();
    formData.append("audio", audioBlob, "input.wav");
    formData.append("language", language); // send selected language for STT

    try {
      const sttRes = await fetch("http://localhost:5000/whisper-stt", {
        method: "POST",
        body: formData,
      });
      const sttData = await sttRes.json();

      if (sttData.transcript) {
        console.log("STT Result:", sttData.transcript);
        sendMessage(sttData.transcript, true);
      } else {
        console.error("STT error:", sttData.error || "No transcript");
      }
    } catch (err) {
      console.error("STT fetch error:", err);
    }
  };

  // 🎤 Start recording audio for STT
  const startRecording = async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: {
          echoCancellation: true,
          noiseSuppression: true,
          autoGainControl: true,
        },
      });
      mediaRecorderRef.current = new MediaRecorder(stream);
      audioChunksRef.current = [];

      // Detect audio activity
      const audioContext = new AudioContext();
      const source = audioContext.createMediaStreamSource(stream);
      const analyser = audioContext.createAnalyser();
      source.connect(analyser);
      const dataArray = new Uint8Array(analyser.fftSize);

      const checkSilence = () => {
        analyser.getByteTimeDomainData(dataArray);
        const isSilent = dataArray.every(
          (val) => Math.abs(val - 128) < 2 // silence threshold
        );
        if (isSilent) {
          if (!silenceTimerRef.current) {
            silenceTimerRef.current = setTimeout(() => {
              stopRecording(); // auto-stop on silence
            }, SILENCE_TIMEOUT);
          }
        } else {
          if (silenceTimerRef.current) {
            clearTimeout(silenceTimerRef.current);
            silenceTimerRef.current = null;
          }
        }
        if (recording) requestAnimationFrame(checkSilence);
      };
      checkSilence();

      mediaRecorderRef.current.ondataavailable = (event) => {
        if (event.data.size > 0) audioChunksRef.current.push(event.data);
      };

      mediaRecorderRef.current.onstop = async () => {
        const audioBlob = new Blob(audioChunksRef.current, {
          type: "audio/wav",
        });
        sendAudioForTranscription(audioBlob);
      };

      mediaRecorderRef.current.start();
      setRecording(true);
    } catch (err) {
      console.error("Mic access error:", err);
    }
  };

  // ⏹ Stop recording
  const stopRecording = () => {
    if (mediaRecorderRef.current && recording) {
      mediaRecorderRef.current.stop();
      setRecording(false);
      if (silenceTimerRef.current) {
        clearTimeout(silenceTimerRef.current);
        silenceTimerRef.current = null;
      }
    }
  };

  return (
    <div className="min-h-screen bg-gradient-to-br p-4">
      <div className="max-w-2xl mx-auto">
        {/* Header */}
        <div className="text-center mb-4">
          <div className="inline-flex items-center justify-center mt-3 bg-gradient-to-b from-gray-50 to-white mb-2 p-2 rounded px-3 shadow-lg">
            <img src="ITC-Hotels-logo.svg" alt="" />
          </div>
        </div>

        {/* Main Chat Container */}
        <div className="bg-white/80 backdrop-blur-sm rounded-3xl shadow-2xl border border-white/20 overflow-hidden">
          {/* Language Selector */}
          <div className="bg-gradient-to-r from-orange-500 to-red-500 p-6">
            <div className="flex items-center justify-between">
              <h2 className="text-white font-semibold text-lg">
                Chat Assistant
              </h2>
              <div className="flex items-center gap-3">
                <label className="text-white/90 font-medium text-sm">
                  Speech Language:
                </label>
                <select
                  value={language}
                  onChange={(e) => setLanguage(e.target.value)}
                  className="bg-white/20 backdrop-blur-sm text-white border border-white/30 rounded-lg px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-white/50 transition-all appearance-none cursor-pointer"
                >
                  <option value="" className="text-gray-800 flex items-center">
                    Auto detect
                  </option>
                  <option
                    value="en"
                    className="text-gray-800"
                  >
                    English
                  </option>
                  <option value="ja" className="text-gray-800">
                    日本語 (Japanese)
                  </option>
                  <option value="hi" className="text-gray-800">
                    हिंदी
                  </option>
                  <option value="gu" className="text-gray-800">
                    ગુજરાતી
                  </option>
                </select>
              </div>
            </div>
          </div>

          {/* Chat Messages */}
          <div
            ref={chatRef}
            className="h-[32rem] overflow-y-auto p-6 space-y-4 bg-gradient-to-b from-gray-50/50 to-white/50"
            style={{ scrollbarWidth: "thin" }}
          >
            {messages.map((m, i) => (
              <div
                key={i}
                className={`flex ${
                  m.role === "user" ? "justify-end" : "justify-start"
                } animate-fade-in`}
              >
                <div
                  className={`max-w-[75%] p-4 rounded-2xl shadow-lg ${
                    m.role === "user"
                      ? "bg-gradient-to-r from-orange-500 to-red-500 text-white rounded-br-md"
                      : "bg-white text-gray-800 rounded-bl-md border-2 border-orange-200 shadow-md"
                  }`}
                >
                  {m.parts.map((part, idx) =>
                    part.image ? (
                      <img
                        key={idx}
                        src={part.image}
                        alt="User upload"
                        className="rounded-xl max-w-full shadow-md max-h-[16rem]"
                      />
                    ) : (
                      <div key={idx} className="text-base leading-relaxed">
                        {parse(part.text)}
                      </div>
                    )
                  )}
                </div>
              </div>
            ))}
          </div>

          {/* Input Area */}
          <div className="p-6 pt-2 bg-white border-t border-gray-100 relative">
            {/* Selected Image Preview */}
            {selectedImage && (
              <div className="absolute bottom-full left-6 right-6 mb-2 bg-gradient-to-r from-gray-50 to-orange-50 rounded-xl shadow-lg z-20">
                <div className="p-1 rounded-lg bg-gradient-to-r from-orange-500 to-red-500">
                  <div className="flex items-center justify-between bg-gradient-to-br from-orange-50 via-amber-50 to-yellow-50 p-2 rounded">
                    <div className="flex items-center gap-3">
                      <img
                        src={URL.createObjectURL(selectedImage)}
                        alt="Selected"
                        className="w-12 h-12 object-cover rounded-lg shadow-md"
                      />
                      <div>
                        <p className="text-blue-700 font-medium text-sm">
                          {selectedImage.name}
                        </p>
                        <p className="text-blue-600 text-xs">
                          {(selectedImage.size / 1024).toFixed(1)} KB
                        </p>
                      </div>
                    </div>
                    <div className="flex gap-2">
                      <button
                        onClick={() => {
                          sendImage();
                          setSelectedImage(null); // Clear the selected image after sending
                        }}
                        className="px-3 py-1.5 bg-blue-500 hover:bg-blue-600 text-white text-sm rounded-lg transition-colors shadow-sm"
                      >
                        Send
                      </button>
                      <button
                        onClick={removeSelectedImage}
                        className="px-3 py-1.5 bg-gray-500 hover:bg-gray-600 text-white text-sm rounded-lg transition-colors shadow-sm"
                      >
                        ✕
                      </button>
                    </div>
                  </div>
                </div>
              </div>
            )}

            {/* Message Input with integrated controls */}
            <div className="relative flex items-center gap-2">
              {/* Attach Menu */}
              <div className="relative">
                <button
                  onClick={() => setShowAttachMenu(!showAttachMenu)}
                  className="p-3 text-gray-500 hover:text-orange-500 hover:bg-orange-50 rounded-full transition-all duration-200"
                  title="Attach file"
                >
                  <svg
                    className="w-5 h-5"
                    fill="none"
                    stroke="currentColor"
                    viewBox="0 0 24 24"
                  >
                    <path
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      strokeWidth={2}
                      d="M12 4v16m8-8H4"
                    />
                  </svg>
                </button>

                {/* Attach Menu Dropdown */}
                {showAttachMenu && (
                  <div className="absolute bottom-full left-0 mb-2 bg-white rounded-lg shadow-lg border border-gray-200 py-2 min-w-[160px] z-10">
                    <button
                      onClick={() => fileInputRef.current?.click()}
                      className="w-full px-4 py-2 text-left text-gray-700 hover:bg-gray-50 flex items-center gap-3 text-sm"
                    >
                      <span className="text-blue-500">📷</span>
                      Upload Image
                    </button>
                  </div>
                )}
              </div>

              {/* Text Input */}
              <div className="flex-1 relative">
                <input
                  type="text"
                  className="w-full p-4 pr-16 border border-gray-200 rounded-2xl text-base placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-orange-500 focus:border-transparent transition-all duration-200 shadow-sm"
                  value={input}
                  onChange={(e) => setInput(e.target.value)}
                  placeholder="Type your message here..."
                  onKeyDown={(e) =>
                    e.key === "Enter" &&
                    !e.shiftKey &&
                    (e.preventDefault(), sendMessage())
                  }
                  autoFocus
                />

                {/* Voice Button inside input */}
                <button
                  className={`absolute right-3 top-1/2 transform -translate-y-1/2 p-2 rounded-full transition-all duration-200 ${
                    recording
                      ? "bg-red-500 text-white shadow-lg animate-pulse"
                      : "text-gray-400 hover:text-orange-500 hover:bg-orange-50"
                  }`}
                  onClick={recording ? stopRecording : startRecording}
                  title={recording ? "Stop Recording" : "Voice Input"}
                >
                  {recording ? (
                    <div className="flex items-center justify-center">
                      <div className="w-4 h-4 bg-white rounded-sm animate-pulse"></div>
                    </div>
                  ) : (
                    <svg
                      className="w-5 h-5"
                      fill="currentColor"
                      viewBox="0 0 24 24"
                    >
                      <path d="M12 14c1.66 0 3-1.34 3-3V5c0-1.66-1.34-3-3-3S9 3.34 9 5v6c0 1.66 1.34 3 3 3z" />
                      <path d="M17 11c0 2.76-2.24 5-5 5s-5-2.24-5-5H5c0 3.53 2.61 6.43 6 6.92V21h2v-3.08c3.39-.49 6-3.39 6-6.92h-2z" />
                    </svg>
                  )}
                </button>
              </div>

              {/* Send Button */}
              <button
                className="p-4 bg-gradient-to-r from-orange-500 to-red-500 hover:from-orange-600 hover:to-red-600 text-white rounded-2xl font-medium transition-all duration-200 shadow-sm disabled:opacity-50 disabled:cursor-not-allowed"
                onClick={() => sendMessage()}
                disabled={!input.trim() && !selectedImage}
              >
                <svg
                  className="w-5 h-5 rotate-90"
                  fill="none"
                  stroke="currentColor"
                  viewBox="0 0 24 24"
                >
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth={2}
                    d="M12 19l9 2-9-18-9 18 9-2zm0 0v-8"
                  />
                </svg>
              </button>

              {/* Hidden file input */}
              <input
                ref={fileInputRef}
                type="file"
                accept="image/*"
                onChange={handleImageSelect}
                className="hidden"
              />
            </div>
          </div>
        </div>

        {/* Footer */}
        <div className="text-center mt-4 text-gray-300 text-sm">
          <p>Powered by ITC Restaurant AI • Always here to help</p>
        </div>
      </div>

      <style jsx="true">{`
        .animate-fade-in {
          animation: fadeIn 0.3s ease-out forwards;
        }
        
        @keyframes fadeIn {
          from {
            opacity: 0;
            transform: translateY(10px);
          }
          to {
            opacity: 1;
            transform: translateY(0);
          }
        }

        /* Hide attach menu when clicking outside */
        document.addEventListener('click', (e) => {
          if (!e.target.closest('.attach-menu')) {
            setShowAttachMenu(false);
          }
        });
        
        /* Custom scrollbar */
        ::-webkit-scrollbar {
          width: 6px;
        }
        
        ::-webkit-scrollbar-track {
          background: #f1f5f9;
          border-radius: 10px;
        }
        
        ::-webkit-scrollbar-thumb {
          background: linear-gradient(to bottom, #f97316, #dc2626);
          border-radius: 10px;
        }
        
        ::-webkit-scrollbar-thumb:hover {
          background: linear-gradient(to bottom, #ea580c, #b91c1c);
        }
      `}</style>
    </div>
  );
};

export default Chatbot;
