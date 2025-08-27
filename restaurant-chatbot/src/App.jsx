import React from "react";
import Chatbot from "./components/ChatBotFinal";

export default function App() {
  return (
    <div className="min-h-screen flex items-center justify-center bg-[url('itc-enterence.jpg')] bg-cover bg-center relative">
      <div className="absolute inset-0 bg-black/40 backdrop-blur-sm"></div>
      <div className="relative z-10  w-full max-w-4xl">
        <Chatbot />
      </div>
    </div>
  );
}
