import React, { useState, useRef, useEffect } from "react";
import parse from "html-react-parser";
import square from "/square-solid-full.svg";
import paperPlane from "/paper-plane-solid-full.svg";
import mic from "/microphone-solid-full.svg";

const Chatbot = () => {
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState("");
  const [isRecording, setIsRecording] = useState(false);
  const [selectedImage, setSelectedImage] = useState(null);
  const chatRef = useRef();
  const mediaRecorderRef = useRef(null);
  const audioChunksRef = useRef([]);

  useEffect(() => {
    if (chatRef.current) {
      chatRef.current.scrollTop = chatRef.current.scrollHeight;
    }
  }, [messages]);

  // 🎤 Start / Stop Recording for STT
  const toggleRecording = async () => {
    if (isRecording) {
      mediaRecorderRef.current.stop();
      setIsRecording(false);
    } else {
      try {
        const stream = await navigator.mediaDevices.getUserMedia({
          audio: true,
        });
        mediaRecorderRef.current = new MediaRecorder(stream);
        audioChunksRef.current = [];

        mediaRecorderRef.current.ondataavailable = (event) => {
          if (event.data.size > 0) {
            audioChunksRef.current.push(event.data);
          }
        };

        mediaRecorderRef.current.onstop = async () => {
          const audioBlob = new Blob(audioChunksRef.current, {
            type: "audio/webm",
          });
          const formData = new FormData();
          formData.append("audio", audioBlob, "recording.webm");
        };

        mediaRecorderRef.current.start();
        setIsRecording(true);
      } catch (err) {
        console.error("Mic access error:", err);
        setMessages((prev) => [
          ...prev,
          {
            role: "model",
            parts: [{ text: "⚠️ Could not access microphone." }],
          },
        ]);
      }
    }
  };

  const sendMessage = async (message = input) => {
    if (!message.trim()) return;

    const newUserMessage = { role: "user", parts: [{ text: message }] };
    setMessages((prev) => [...prev, newUserMessage]);
    setInput("");

    try {
      const response = await fetch("http://localhost:5000/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message }),
      });

      const data = await response.json();
      if (data.error) {
        setMessages((prev) => [
          ...prev,
          { role: "model", parts: [{ text: `❌ ${data.error}` }] },
        ]);
      } else {
        const botMsg = { role: "model", parts: [{ text: data.response }] };
        setMessages((prev) => [...prev, botMsg]);
        speakText(data.response); // 🔊 TTS
      }
    } catch (err) {
      setMessages((prev) => [
        ...prev,
        { role: "model", parts: [{ text: `⚠️ Error: ${err.message}` }] },
      ]);
    }
  };

  // 🖼️ Send image
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
        speakText(data.response); // 🔊 TTS
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

  // 🔊 Text-to-Speech
  const speakText = async (text) => {
    try {
      const res = await fetch("http://localhost:5000/tts", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text }),
      });

      const data = await res.json();
      if (data.audio) {
        const audio = new Audio(`data:audio/mpeg;base64,${data.audio}`);
        audio.play();
      }
    } catch (err) {
      console.error("TTS error:", err);
    }
  };

  return (
    <div className="w-lg p-6 bg-gray-50 rounded-2xl shadow-lg font-sans max-w-xl mx-auto mt-10">
      <h2 className="text-2xl font-semibold text-center mb-4">
        ITC Restaurant Chatbot
      </h2>

      {/* Chat messages */}
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

      {/* Image upload */}
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

      {/* Input + Controls */}
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
          className={`px-4 py-2 rounded-lg transition ${
            isRecording
              ? "bg-red-500 hover:bg-red-600"
              : "bg-gray-400 hover:bg-gray-700"
          } text-white`}
          onClick={toggleRecording}
        >
          {isRecording ? (
            <img src={square} alt="Stop" className="w-6 h-6 inline-block" />
          ) : (
            <img src={mic} alt="Mic" className="w-6 h-6 inline-block" />
          )}
        </button>
        <button
          className="px-4 py-2 bg-gray-400 text-white rounded-lg hover:bg-gray-600 transition"
          onClick={() => sendMessage()}
        >
          <img src={paperPlane} alt="Send" className="w-5 h-5 inline-block" />
        </button>
      </div>
    </div>
  );
};

export default Chatbot;
