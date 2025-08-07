import React, { useState, useRef, useEffect } from "react";
import parse from "html-react-parser";
import square from "/square-solid-full.svg";
import paperPlane from "/paper-plane-solid-full.svg";
import mic from "/microphone-solid-full.svg";
const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;

const Chatbot = () => {
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState("");
  const [isListening, setIsListening] = useState(false);
  const chatRef = useRef();
  const recognitionRef = useRef(null);

  useEffect(() => {
    if (chatRef.current) {
      chatRef.current.scrollTop = chatRef.current.scrollHeight;
    }
  }, [messages]);

  useEffect(() => {
    if (SpeechRecognition) {
      recognitionRef.current = new SpeechRecognition();
      recognitionRef.current.continuous = false;
      recognitionRef.current.interimResults = false;
      recognitionRef.current.lang = "";

      recognitionRef.current.onresult = (event) => {
        const transcript = event.results[0][0].transcript;
        setInput(transcript);
        setIsListening(false);
        if (transcript.trim()) {
          sendMessage(transcript);
        }
      };

      recognitionRef.current.onerror = (event) => {
        console.error("Speech recognition error:", event.error);
        setIsListening(false);
        setMessages((prev) => [
          ...prev,
          {
            role: "model",
            parts: [{ text: "⚠️ Speech recognition error. Please try again." }],
          },
        ]);
      };

      recognitionRef.current.onend = () => {
        setIsListening(false);
      };
    }

    return () => {
      if (recognitionRef.current) {
        recognitionRef.current.stop();
      }
    };
  },[]);

  const toggleSpeechRecognition = () => {
    if (!SpeechRecognition) {
      setMessages((prev) => [
        ...prev,
        {
          role: "model",
          parts: [{ text: "⚠️ Speech recognition is not supported in this browser." }],
        },
      ]);
      return;
    }

    if (isListening) {
      recognitionRef.current.stop();
    } else {
      recognitionRef.current.start();
      setIsListening(true);
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
        setMessages((prev) => [
          ...prev,
          { role: "model", parts: [{ text: data.response }] },
        ]);
      }
    } catch (err) {
      setMessages((prev) => [
        ...prev,
        {
          role: "model",
          parts: [{ text: `⚠️ Error: ${err.message}` }],
        },
      ]);
    }
  };

  return (
    <div className="w-lg p-6 bg-gray-50 rounded-2xl shadow-lg font-sans max-w-xl mx-auto mt-10">
      <h2 className="text-2xl font-semibold text-center mb-4">
        ITC Restaurant Chatbot
      </h2>

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
            <div className="text-base text-gray-800">{parse(m.parts[0]?.text)}</div>
          </div>
        ))}
      </div>

      <div className="flex items-center gap-2">
        <input
          type="text"
          className="flex-1 p-3 border rounded-lg text-base shadow-sm focus:outline-none focus:ring-2 focus:ring-blue-400"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="Type or speak your message..."
          onKeyDown={(e) => e.key === "Enter" && sendMessage()}
        />
        <button
          className={`px-4 py-2 rounded-lg transition ${
            isListening ? "bg-gray-400 hover:bg-gray-600" : "bg-gray-400 hover:bg-gray-700"
          } text-white`}
          onClick={toggleSpeechRecognition}
          disabled={!SpeechRecognition}
        >
          {isListening ? <img src={square} alt="pause" className="w-6 h-6 inline-block" /> : <img src={mic} alt="mic" className="w-6 h-6 inline-block"  />}
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