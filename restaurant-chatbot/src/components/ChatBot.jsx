import React, { useState, useRef, useEffect, useCallback } from "react";
import parse from "html-react-parser";

const Chatbot = () => {
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState("");
  const [recording, setRecording] = useState(false);
  const [language, setLanguage] = useState("en");
  const [selectedImage, setSelectedImage] = useState(null);
  const chatRef = useRef();
  const fileInputRef = useRef();

  // Scroll chat to bottom
  useEffect(() => {
    if (chatRef.current) {
      chatRef.current.scrollTop = chatRef.current.scrollHeight;
    }
  }, [messages]);

  // Unique ID per user
  const [userId] = useState(() => {
    let storedId = localStorage.getItem("chat_user_id");
    if (!storedId) {
      storedId = `user_${Math.random().toString(36).substring(2, 10)}`;
      localStorage.setItem("chat_user_id", storedId);
    }
    return storedId;
  });

  const stripHTML = (html) => {
    const temp = document.createElement("div");
    temp.innerHTML = html;
    return temp.textContent || temp.innerText || "";
  };

  // Text-to-Speech (TTS)
  const speak = useCallback(
    (text) => {
      if (!window.speechSynthesis) {
        console.warn("TTS not supported in this browser.");
        return;
      }

      // Cancel ongoing speech
      window.speechSynthesis.cancel();
      const utterance = new SpeechSynthesisUtterance(text);
      const voices = window.speechSynthesis.getVoices();
      let voice = null;

      // Set language based on user selection
      if (language === "hi") {
        utterance.lang = "hi-IN";
      } else if (language === "gu") {
        voice = voices.find((v) => v.lang.startsWith("gu"));
        // If Gujarati voice not found → fallback to Hindi
        if (!voice) {
          voice = voices.find((v) => v.lang.startsWith("hi")) || voices[0];
          utterance.lang = "hi-IN";
        } else {
          utterance.lang = "gu-IN";
        }
      } else {
        utterance.lang = "en-US";
      }

      utterance.rate = 1;
      utterance.pitch = 1;

      window.speechSynthesis.speak(utterance);
    },
    [language] // ✅ re-create only if language changes
  );

  // Send text message
  const sendMessage = useCallback(
    async (customInput) => {
      const messageToSend = customInput || input;
      if (!messageToSend.trim()) return;

      const newUserMessage = { role: "user", parts: [{ text: messageToSend }] };
      setMessages((prev) => [...prev, newUserMessage]);
      setInput("");

      try {
        const response = await fetch("http://localhost:5000/chat", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            message: messageToSend,
            language,
            user_id: userId,
          }),
        });

        const data = await response.json();
        const botReply = data.response || `${data.error}`;

        setMessages((prev) => [
          ...prev,
          { role: "model", parts: [{ text: botReply }] },
        ]);

        speak(stripHTML(botReply));
      } catch (err) {
        setMessages((prev) => [
          ...prev,
          { role: "model", parts: [{ text: `⚠️ Error: ${err.message}` }] },
        ]);
      }
    },
    [input, language, userId, speak]
  );

  // Send selected image
  const sendImage = async () => {
    if (!selectedImage) return;

    // preview in chat
    const previewUrl = URL.createObjectURL(selectedImage);
    setMessages((prev) => [
      ...prev,
      {
        role: "user",
        parts: [{ text: input || "Sent an image" }],
        image: previewUrl,
      },
    ]);
    setInput("");

    const formData = new FormData();
    formData.append("image", selectedImage);
    formData.append("prompt", input || "Describe this image");
    formData.append("language", language);
    formData.append("user_id", userId);

    try {
      const res = await fetch("http://localhost:5000/image-chat", {
        method: "POST",
        body: formData,
      });
      const data = await res.json();
      const botReply = data.response || `${data.error}`;

      setMessages((prev) => [
        ...prev,
        { role: "model", parts: [{ text: botReply }] },
      ]);

      // Speak the reply
      speak(stripHTML(botReply));
    } catch (err) {
      setMessages((prev) => [
        ...prev,
        { role: "model", parts: [{ text: `Error: ${err.message}` }] },
      ]);
    } finally {
      setSelectedImage(null);
    }
  };

  // Voice input
  const startRecording = () => {
    const SpeechRecognition =
      window.SpeechRecognition || window.webkitSpeechRecognition;

    if (!SpeechRecognition) {
      alert("Speech Recognition not supported in this browser.");
      return;
    }

    const recognition = new SpeechRecognition();
    recognition.lang =
      language === "hi" ? "hi-IN" : language === "gu" ? "gu-IN" : "en-US";
    recognition.interimResults = false;
    recognition.maxAlternatives = 1;

    recognition.onstart = () => setRecording(true);
    recognition.onend = () => setRecording(false);

    recognition.onresult = (event) => {
      const transcript = event.results[0][0].transcript;
      sendMessage(transcript);
    };

    recognition.onerror = (event) => {
      console.error("STT error:", event.error);
      setRecording(false);
    };

    recognition.start();
  };

  const stopSpeaking = () => {
    if (window.speechSynthesis.speaking) {
      window.speechSynthesis.cancel();
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

        {/* Chatbox */}
        <div className="bg-white/80 backdrop-blur-sm rounded-3xl shadow-2xl border border-white/20 overflow-hidden">
          {/* Language Selector */}
          <div className="bg-gradient-to-r from-orange-500 to-red-500 p-6">
            <div className="flex items-center justify-between">
              <h2 className="text-white font-semibold text-lg">
                Chat Assistant
              </h2>
              <div className="flex items-center gap-3">
                <label className="text-white/90 font-medium text-sm">
                  Language:
                </label>
                <select
                  value={language}
                  onChange={(e) => setLanguage(e.target.value)}
                  className="bg-white/20 backdrop-blur-sm text-white border border-white/30 rounded-lg px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-white/50 transition-all appearance-none cursor-pointer"
                >
                  <option
                    value="en"
                    className="text-gray-800 flex items-center"
                  >
                    English
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

          {/* Messages */}
          <div
            ref={chatRef}
            className="h-[32rem] overflow-y-auto p-6 space-y-4 bg-gradient-to-b from-gray-50/50 to-white/50"
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
                      ? "bg-gradient-to-r from-orange-500 to-red-500 text-white"
                      : "bg-white text-gray-800 border-2 border-orange-200"
                  }`}
                >
                  {m.image && (
                    <img
                      src={m.image}
                      alt="uploaded"
                      className="rounded-xl mb-2 max-h-48"
                    />
                  )}
                  {m.parts.map((part, idx) => (
                    <div key={idx} className="text-base leading-relaxed">
                      {parse(part.text)}
                    </div>
                  ))}
                  {m.role === "model" && (
                    <div className="flex gap-2 mt-2">
                      <button
                        onClick={() =>
                          speak(stripHTML(m.parts.map((p) => p.text).join(" ")))
                        }
                        className="flex items-center gap-2 px-3 py-1.5 rounded-full bg-orange-100 text-orange-600 hover:bg-orange-200 transition"
                      >
                        <svg
                          className="w-4 h-4"
                          fill="currentColor"
                          viewBox="0 0 24 24"
                        >
                          <path d="M12 14c1.66 0 3-1.34 3-3V5c0-1.66-1.34-3-3-3S9 3.34 9 5v6c0 1.66 1.34 3 3 3z" />
                          <path d="M17 11c0 2.76-2.24 5-5 5s-5-2.24-5-5H5c0 3.53 2.61 6.43 6 6.92V21h2v-3.08c3.39-.49 6-3.39 6-6.92h-2z" />
                        </svg>
                      </button>

                      <button
                        onClick={stopSpeaking}
                        className="flex items-center gap-2 px-3 py-1.5 rounded-full bg-red-100 text-red-600 hover:bg-red-200 transition"
                      >
                        <svg
                          className="w-4 h-4"
                          fill="currentColor"
                          viewBox="0 0 24 24"
                        >
                          <rect x="6" y="6" width="12" height="12" rx="2" />
                        </svg>
                      </button>
                    </div>
                  )}
                </div>
              </div>
            ))}
          </div>

          {/* Input */}
          <div className="p-6 pt-2 bg-white border-t border-gray-100 relative">
            {selectedImage && (
              <div className="absolute bottom-full left-6 right-6 mb-2 bg-orange-50 rounded-xl shadow-lg p-3 flex items-center justify-between">
                <div className="flex items-center gap-3">
                  <img
                    src={URL.createObjectURL(selectedImage)}
                    alt="preview"
                    className="w-12 h-12 object-cover rounded-lg"
                  />
                  <div>
                    <p className="text-sm font-medium">{selectedImage.name}</p>
                    <p className="text-xs text-gray-500">
                      {(selectedImage.size / 1024).toFixed(1)} KB
                    </p>
                  </div>
                </div>
                <div className="flex gap-2">
                  <button
                    onClick={sendImage}
                    className="px-3 py-1.5 bg-blue-500 hover:bg-blue-600 text-white text-sm rounded-lg"
                  >
                    Send
                  </button>
                  <button
                    onClick={() => setSelectedImage(null)}
                    className="px-3 py-1.5 bg-gray-500 hover:bg-gray-600 text-white text-sm rounded-lg"
                  >
                    ✕
                  </button>
                </div>
              </div>
            )}

            <div className="flex items-center gap-2">
              {/* Text input */}
              <div className="flex-1 relative">
                <input
                  type="text"
                  className="w-full p-4 pr-20 border rounded-2xl text-base"
                  value={input}
                  onChange={(e) => setInput(e.target.value)}
                  placeholder="Type your message..."
                  onKeyDown={(e) =>
                    e.key === "Enter" && (e.preventDefault(), sendMessage())
                  }
                />

                {/* Mic button */}
                <button
                  className={`absolute right-10 top-1/2 -translate-y-1/2 p-2 rounded-full ${
                    recording
                      ? "bg-red-500 text-white animate-pulse"
                      : "text-gray-400 hover:text-orange-500"
                  }`}
                  onClick={startRecording}
                  title="Voice Input"
                >
                  <svg
                    className="w-5 h-5"
                    fill="currentColor"
                    viewBox="0 0 24 24"
                  >
                    <path d="M12 14c1.66 0 3-1.34 3-3V5c0-1.66-1.34-3-3-3S9 3.34 9 5v6c0 1.66 1.34 3 3 3z" />
                    <path d="M17 11c0 2.76-2.24 5-5 5s-5-2.24-5-5H5c0 3.53 2.61 6.43 6 6.92V21h2v-3.08c3.39-.49 6-3.39 6-6.92h-2z" />
                  </svg>
                </button>

                {/* Image button */}
                <button
                  className="absolute right-0 top-1/2 -translate-y-1/2 p-2 rounded-full text-gray-400 hover:text-orange-500"
                  onClick={() => fileInputRef.current.click()}
                  title="Upload Image"
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
                <input
                  type="file"
                  accept="image/*"
                  ref={fileInputRef}
                  style={{ display: "none" }}
                  onChange={(e) => setSelectedImage(e.target.files[0])}
                />
              </div>

              {/* Send button */}
              <button
                className="p-4 bg-gradient-to-r from-orange-500 to-red-500 text-white rounded-2xl"
                onClick={() => sendMessage()}
              >
                ➤
              </button>
            </div>
          </div>
        </div>

        {/* Footer */}
        <div className="text-center mt-4 text-gray-300 text-sm">
          Powered by ITC Restaurant AI
        </div>
      </div>
    </div>
  );
};

export default Chatbot;
