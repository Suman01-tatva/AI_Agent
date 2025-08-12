import React, { useState, useRef, useEffect, useCallback } from "react";
import parse from "html-react-parser";

const Chatbot = () => {
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState("");
  const [recording, setRecording] = useState(false);
  const [language, setLanguage] = useState("en"); // 🌍 Selected language
  const chatRef = useRef();
  const mediaRecorderRef = useRef(null);
  const audioChunksRef = useRef([]);
  const silenceTimerRef = useRef(null);
  const [selectedImage, setSelectedImage] = useState(null);

  const SILENCE_TIMEOUT = 1500; // ms of silence before auto-stop

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
      parts: [
        { text: input || "Image uploaded" },
        { image: URL.createObjectURL(selectedImage) },
      ],
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
    async (customInput) => {
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
          body: JSON.stringify({ message: messageToSend, language }), // send selected language
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

        // Step 2: Play bot reply via TTS
        const ttsRes = await fetch("http://localhost:5000/tts", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ text: botReply, language }), // send language for TTS
        });

        const ttsData = await ttsRes.json();
        if (ttsData.audio) {
          const audio = new Audio(`data:audio/mpeg;base64,${ttsData.audio}`);
          audio.play();
        } else {
          console.error("TTS error:", ttsData.error || "Unknown error");
        }
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
      const sttRes = await fetch("http://localhost:5000/stt", {
        method: "POST",
        body: formData,
      });
      const sttData = await sttRes.json();

      if (sttData.transcript) {
        sendMessage(sttData.transcript);
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
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
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
    <div className="w-lg p-6 bg-gray-50 rounded-2xl shadow-lg font-sans max-w-xl mx-auto mt-10">
      <h2 className="text-2xl font-semibold text-center mb-4">
        🍽️ ITC Restaurant Chatbot
      </h2>

      {/* 🌍 Language selector */}
      <div className="mb-4">
        <label className="block mb-1 font-medium text-gray-700">
          Select Language:
        </label>
        <select
          value={language}
          onChange={(e) => setLanguage(e.target.value)}
          className="p-2 border rounded-lg"
        >
          <option value="en">English</option>
          <option value="hi">Hindi</option>
          <option value="gu">Gujarati</option>
        </select>
      </div>

      <div
        ref={chatRef}
        className="h-96 overflow-y-auto bg-white border border-gray-200 rounded-xl p-4 mb-4 space-y-4"
      >
        {messages.map((m, i) => (
          <div
            key={i}
            className={`max-w-[80%] p-3 rounded-xl ${
              m.role === "user"
                ? "bg-blue-100 self-end ml-auto text-right"
                : "bg-gray-200 self-start mr-auto text-left"
            }`}
          >
            {m.parts.map((part, idx) =>
              part.image ? (
                <img
                  key={idx}
                  src={part.image}
                  alt="User upload"
                  className="rounded-lg max-w-full mt-2"
                />
              ) : (
                <div key={idx} className="text-base text-gray-800">
                  {parse(part.text)}
                </div>
              )
            )}
          </div>
        ))}
      </div>

      <div className="flex items-center gap-2 mb-2">
        <input
          type="file"
          accept="image/*"
          onChange={(e) => setSelectedImage(e.target.files[0])}
          className="flex-1 p-2 border rounded-lg text-sm"
        />
        {selectedImage && (
          <button
            className="px-4 py-2 bg-green-500 text-white rounded-lg hover:bg-green-600 transition"
            onClick={sendImage}
          >
            Send Image
          </button>
        )}
      </div>

      <div className="flex items-center gap-2">
        <input
          type="text"
          className="flex-1 p-3 border rounded-lg text-base shadow-sm focus:outline-none focus:ring-2 focus:ring-blue-400"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="Type your message..."
          onKeyDown={(e) => e.key === "Enter" && sendMessage()}
        />

        <button
          className={`flex items-center gap-1 px-4 py-2 rounded-lg transition ${
            recording ? "bg-red-600" : "bg-green-600"
          } text-white hover:opacity-90`}
          onClick={recording ? stopRecording : startRecording}
          title={recording ? "Stop Recording" : "Start Recording"}
        >
          🎤
          <span className="text-sm">
            {recording ? "Recording..." : "Speak now"}
          </span>
        </button>

        <button
          className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition"
          onClick={() => sendMessage()}
        >
          Send
        </button>
      </div>
    </div>
  );
};

export default Chatbot;
