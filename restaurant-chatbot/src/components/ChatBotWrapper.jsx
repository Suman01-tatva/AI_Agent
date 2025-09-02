import React, { useState } from "react";
import ChatBotFinal from "./ChatBotFinal";

export default function ChatBotWrapper() {
  const [open, setOpen] = useState(false);

  return (
    <div>
      {/* Floating launcher button */}
      <button
        onClick={() => setOpen(!open)}
        style={{
          position: "fixed",
          bottom: "20px",
          right: "20px",
          backgroundColor: "#2563eb", // Tailwind blue-600
          color: "white",
          borderRadius: "50%",
          width: "56px",
          height: "56px",
          boxShadow: "0 4px 12px rgba(0,0,0,0.2)",
          fontSize: "24px",
          zIndex: 10000,
        }}
      >
        💬
      </button>

      {/* Popup chat window */}
      {open && (
        <div
          style={{
            position: "fixed",
            bottom: "90px",
            right: "20px",
            overflow: "hidden",
            zIndex: 10000,
          }}
        >
          <ChatBotFinal />
        </div>
      )}
    </div>
  );
}
