import React, { useState, useRef, useEffect, useCallback } from "react";
import parse from "html-react-parser";
import itc_logo from "../../public/ITC-Hotels-logo.svg"

const params = new URLSearchParams(window.location.search);
const userId = params.get("user_id") || "default_user";
const appId = params.get("app_id") || "default_app";
const threadId = appId + "_" + userId;

const ChatBotFinal = () => {
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [recording, setRecording] = useState(false);
  const [language, setLanguage] = useState("en");
  const [selectedImage, setSelectedImage] = useState(null);
  const [imagePreview, setImagePreview] = useState(null);
  const [selectedFiles, setSelectedFiles] = useState([]);
  const [uploadingDocs, setUploadingDocs] = useState(false);

  const fileInputRef = useRef(null);
  const docInputRef = useRef(null);
  const messagesEndRef = useRef(null);
  const mediaRecorderRef = useRef(null);
  const audioChunksRef = useRef([]);
  const silenceTimerRef = useRef(null);

  // Commented Web Speech API refs for future use
  // const recognitionRef = useRef(null);
  // const [isListening, setIsListening] = useState(false);

  // Commented Web Speech API for STT (backup - not used currently)
  /*
    const startListening = () => {
        if (isListening) {
        stopListening();
        return;
        }

        setIsListening(true);
        const recognition = new (window.SpeechRecognition || window.webkitSpeechRecognition)();
        recognition.lang = language === "en" ? "en-US" : language === "hi" ? "hi-IN" : "en-US";
        recognition.continuous = true;
        recognition.interimResults = true;

        recognition.onresult = (event) => {
        let transcript = "";
        for (let i = event.resultIndex; i < event.results.length; i++) {
            transcript += event.results[i][0].transcript;
        }
        setInput(transcript);
        };

        recognition.onend = () => {
        setIsListening(false);
        };

        recognition.onerror = () => {
        setIsListening(false);
        };

        recognitionRef.current = recognition;
        recognition.start();
    };

    const stopListening = () => {
        if (recognitionRef.current) {
        recognitionRef.current.stop();
        }
        setIsListening(false);
    };
    */

  const SILENCE_TIMEOUT = 1500;

  // Auto-scroll to bottom when new messages arrive
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  // Handle image selection
  const handleImageSelect = (e) => {
    const file = e.target.files[0];
    if (!file) return;

    setSelectedImage(file);
    const reader = new FileReader();
    reader.onload = (e) => {
      setImagePreview(e.target.result);
    };
    reader.readAsDataURL(file);
  };

  const removeImage = () => {
    setSelectedImage(null);
    setImagePreview(null);
    if (fileInputRef.current) {
      fileInputRef.current.value = "";
    }
  };

  // Handle document file selection
  const handleDocumentSelect = (e) => {
    const files = Array.from(e.target.files);
    if (!files.length) return;

    const supportedFiles = files.filter((file) => {
      const ext = file.name.toLowerCase();
      return (
        ext.endsWith(".json") || ext.endsWith(".pdf") || ext.endsWith(".docx")
      );
    });

    if (supportedFiles.length !== files.length) {
      alert(
        "Some files were skipped. Only JSON, PDF, and DOCX files are supported."
      );
    }

    setSelectedFiles((prev) => [...prev, ...files]);
  };

  const removeDocument = (index) => {
    setSelectedFiles((prev) => prev.filter((_, i) => i !== index));
  };

  const clearDocuments = () => {
    setSelectedFiles([]);
    if (docInputRef.current) {
      docInputRef.current.value = "";
    }
  };

  // Upload documents to backend
  const uploadDocuments = async () => {
    if (selectedFiles.length === 0) {
      alert("Please select files to upload.");
      return;
    }

    setUploadingDocs(true);

    try {
      const formData = new FormData();
      selectedFiles.forEach((file) => {
        formData.append("files", file);
      });

      const res = await fetch("http://192.168.1.71:5000/add-docs", {
        method: "POST",
        body: formData,
      });

      if (!res.ok) {
        const errData = await res.json();
        throw new Error(errData.detail || "Unknown server error");
      }

      const data = await res.json();
      const successMessage = {
        role: "model",
        parts: [
          {
            text: `✅ Successfully uploaded ${selectedFiles.length} file(s) and added ${data.added} document chunks to the knowledge base.`,
          },
        ],
        timestamp: new Date().toLocaleTimeString([], {
          hour: "2-digit",
          minute: "2-digit",
        }),
      };

      setMessages((prev) => [...prev, successMessage]);
      clearDocuments();
    } catch (err) {
      console.error(err);
      const errorMessage = {
        role: "model",
        parts: [{ text: "❌ Failed to upload documents. Please try again." }],
        timestamp: new Date().toLocaleTimeString([], {
          hour: "2-digit",
          minute: "2-digit",
        }),
      };
      setMessages((prev) => [...prev, errorMessage]);
    }

    setUploadingDocs(false);
  };

  // Start recording audio for STT
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

      const audioContext = new AudioContext();
      const source = audioContext.createMediaStreamSource(stream);
      const analyser = audioContext.createAnalyser();
      source.connect(analyser);
      const dataArray = new Uint8Array(analyser.fftSize);

      const checkSilence = () => {
        analyser.getByteTimeDomainData(dataArray);
        const isSilent = dataArray.every((val) => Math.abs(val - 128) < 2);
        if (isSilent) {
          if (!silenceTimerRef.current) {
            silenceTimerRef.current = setTimeout(() => {
              stopRecording();
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

  // Handle STT sending
  const sendAudioForTranscription = async (audioBlob) => {
    const formData = new FormData();
    formData.append("audio", audioBlob, "input.wav");
    formData.append("language", language);

    try {
      const sttRes = await fetch("http://192.168.1.71:5000/whisper-stt", {
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
      console.error("STT error:", err);
    }
  };

  const playAudio = useCallback(async (botReply) => {
    try {
      const ttsRes = await fetch("http://192.168.1.71:5000/gemini-tts", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text: botReply, language }),
      });

      const ttsData = await ttsRes.json();
      if (ttsData.audio) {
        const audio = new Audio(`data:audio/mpeg;base64,${ttsData.audio}`);
        audio.play();
      }
    } catch (err) {
      console.error("TTS error:", err);
    }
  }, [language]);
  
  // Send image message
  const sendImage = useCallback(async () => {
    if (!selectedImage) return;

    setLoading(true);
    const imageMessage = {
      role: "user",
      parts: [{ text: input }, { image: imagePreview }],
      timestamp: new Date().toLocaleTimeString([], {
        hour: "2-digit",
        minute: "2-digit",
      }),
    };
    setMessages((prev) => [...prev, imageMessage]);
    setInput("");

    const formData = new FormData();
    formData.append("file", selectedImage);
    formData.append("question", input || "Describe this image");
    formData.append("thread_id", threadId);
    try {
      const res = await fetch("http://192.168.1.71:5000/image-chat", {
        method: "POST",
        body: formData,
      });

      const data = await res.json();
      if (data.error) {
        setMessages((prev) => [
          ...prev,
          {
            role: "model",
            parts: [{ text: `❌ ${data.error}` }],
            timestamp: new Date().toLocaleTimeString([], {
              hour: "2-digit",
              minute: "2-digit",
            }),
          },
        ]);
      } else {
        const botMsg = {
          role: "model",
          parts: [{ text: data.response }],
          timestamp: new Date().toLocaleTimeString([], {
            hour: "2-digit",
            minute: "2-digit",
          }),
        };
        setMessages((prev) => [...prev, botMsg]);
      }
    } catch (err) {
      setMessages((prev) => [
        ...prev,
        {
          role: "model",
          parts: [{ text: `⚠️ Error: ${err.message}` }],
          timestamp: new Date().toLocaleTimeString([], {
            hour: "2-digit",
            minute: "2-digit",
          }),
        },
      ]);
    } finally {
      removeImage();
      setLoading(false);
    }
  }, [selectedImage, imagePreview, input]);

  // Send message to chatbot
  const sendMessage = useCallback(
    async (customInput , speak = false) => {
      if (selectedImage) {
        sendImage();
        return;
      }

      const newMessage = input || customInput;
      if (!newMessage.trim()) return;

      setLoading(true);
      const newUserMessage = {
        role: "user",
        parts: [{ text: newMessage }],
        timestamp: new Date().toLocaleTimeString([], {
          hour: "2-digit",
          minute: "2-digit",
        }),
      };
      setMessages((prev) => [...prev, newUserMessage]);
      setInput("");

      try {
        const response = await fetch("http://192.168.1.71:5000/chat", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ message: newMessage, thread_id: threadId }),
        });

        const data = await response.json();
        if (data.error) {
          setMessages((prev) => [
            ...prev,
            {
              role: "model",
              parts: [{ text: `❌ ${data.error}` }],
              timestamp: new Date().toLocaleTimeString([], {
                hour: "2-digit",
                minute: "2-digit",
              }),
            },
          ]);
          return;
        }

        const botReply = data.response;
        setMessages((prev) => [
          ...prev,
          {
            role: "model",
            parts: [{ text: botReply }],
            timestamp: new Date().toLocaleTimeString([], {
              hour: "2-digit",
              minute: "2-digit",
            }),
          },
        ]);

        // TTS if needed
        if (speak) playAudio(botReply);
      } catch (err) {
        setMessages((prev) => [
          ...prev,
          { role: "model", parts: [{ text: `⚠️ Error: ${err.message}` }] },
        ]);
      } finally {
        setLoading(false);
      }
    },
    [input, selectedImage, sendImage, playAudio]
  );

  const getFileIcon = (filename) => {
    const ext = filename.toLowerCase();
    if (ext.endsWith(".pdf")) {
      return (
        <svg
          className="w-4 h-4 text-red-500"
          fill="currentColor"
          viewBox="0 0 20 20"
        >
          <path
            fillRule="evenodd"
            d="M4 4a2 2 0 012-2h4.586A2 2 0 0112 2.586L15.414 6A2 2 0 0116 7.414V16a2 2 0 01-2 2H6a2 2 0 01-2-2V4zm2 6a1 1 0 011-1h6a1 1 0 110 2H7a1 1 0 01-1-1zm1 3a1 1 0 100 2h6a1 1 0 100-2H7z"
            clipRule="evenodd"
          />
        </svg>
      );
    } else if (ext.endsWith(".docx")) {
      return (
        <svg
          className="w-4 h-4 text-blue-500"
          fill="currentColor"
          viewBox="0 0 20 20"
        >
          <path
            fillRule="evenodd"
            d="M4 4a2 2 0 012-2h4.586A2 2 0 0112 2.586L15.414 6A2 2 0 0116 7.414V16a2 2 0 01-2 2H6a2 2 0 01-2-2V4z"
            clipRule="evenodd"
          />
        </svg>
      );
    } else if (ext.endsWith(".json")) {
      return (
        <svg
          className="w-4 h-4 text-yellow-500"
          fill="currentColor"
          viewBox="0 0 20 20"
        >
          <path
            fillRule="evenodd"
            d="M3 4a1 1 0 011-1h12a1 1 0 011 1v2a1 1 0 01-1 1H4a1 1 0 01-1-1V4zM3 10a1 1 0 011-1h6a1 1 0 011 1v6a1 1 0 01-1 1H4a1 1 0 01-1-1v-6zM14 9a1 1 0 00-1 1v6a1 1 0 001 1h2a1 1 0 001-1v-6a1 1 0 00-1-1h-2z"
            clipRule="evenodd"
          />
        </svg>
      );
    }
    return (
      <svg
        className="w-4 h-4 text-gray-500"
        fill="currentColor"
        viewBox="0 0 20 20"
      >
        <path
          fillRule="evenodd"
          d="M4 4a2 2 0 012-2h4.586A2 2 0 0112 2.586L15.414 6A2 2 0 0116 7.414V16a2 2 0 01-2 2H6a2 2 0 01-2-2V4z"
          clipRule="evenodd"
        />
      </svg>
    );
  };

  return (
    <div className="flex justify-center">
      <div className="flex flex-col h-[85vh] w-full max-w-2xl rounded-3xl shadow-lg overflow-hidden border border-gray-200">
        {/* Header */}
        <div className="inline-flex items-center justify-between bg-gradient-to-b from-gray-50 to-white p-2 px-5 rounded shadow-lg">
          <img src={itc_logo} alt="" />
          <div className="flex items-center">
            {/* Language Selector (from first code) */}
            <div className="flex items-center gap-2">
              <label className="text-gray-600 font-medium text-sm">
                Speech Language:
              </label>
              <select
                value={language}
                onChange={(e) => setLanguage(e.target.value)}
                className="bg-gray-50 text-gray-700 border border-gray-200 rounded-lg px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 transition-all cursor-pointer"
              >
                <option value="">Auto detect</option>
                <option value="en">English</option>
                <option value="ja">日本語 (Japanese)</option>
                <option value="hi">हिंदी</option>
                <option value="gu">ગુજરાતી</option>
              </select>
            </div>

            {/* <button
              onClick={() => docInputRef.current?.click()}
              className="p-2 text-gray-400 hover:text-gray-600 transition-colors rounded-lg"
              title="Upload Documents (PDF, DOCX, JSON)"
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
                  d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"
                />
              </svg>
            </button> */}
          </div>
        </div>

        {/* Chat Window */}
        <div className="flex-1 overflow-y-auto px-6">
          {messages.length === 0 && (
            <div className="py-6">
              <div className="mb-6">
                <p className="text-gray-600 text-base leading-relaxed mb-6">
                  Hi 👋 I am a smart chat bot, I can process image and text!
                </p>
              </div>
            </div>
          )}

          {messages.map((msg, idx) => (
            <div key={idx} className={`py-1 ${idx === 0 ? "pt-6" : ""}`}>
              <div
                className={`flex ${
                  msg.role === "user" ? "justify-end" : "justify-start"
                }`}
              >
                <div
                  className={`max-w-[80%] ${
                    msg.role === "user"
                      ? "bg-gray-900 text-white rounded-3xl rounded-br-lg"
                      : "bg-gray-300 text-gray-800 rounded-3xl rounded-bl-lg"
                  } px-4 py-4`}
                >
                  {msg.parts.length>1 && msg.parts[1].image && (
                    <div className="mb-2">
                      <img
                        src={msg.parts[1].image}
                        alt="Shared image"
                        className="w-full max-w-xs h-64 object-cover rounded-2xl"
                      />
                    </div>
                  )}
                  <div className="text-sm leading-relaxed whitespace-pre-wrap">
                    {parse(msg.parts[0].text)}
                  </div>
                </div>
              </div>
              {msg.timestamp && (
                <div
                  className={`text-xs text-gray-400 mt-2 ${
                    msg.role === "user" ? "text-right" : "text-left"
                  }`}
                >
                  {msg.timestamp}
                </div>
              )}
            </div>
          ))}

          {loading && (
            <div className="py-4">
              <div className="flex justify-start">
                <div className="bg-gray-50 rounded-3xl rounded-bl-lg px-6 py-4">
                  <div className="flex items-center space-x-2">
                    <div className="flex space-x-1">
                      <div className="w-2 h-2 bg-gray-400 rounded-full animate-bounce"></div>
                      <div
                        className="w-2 h-2 bg-gray-400 rounded-full animate-bounce"
                        style={{ animationDelay: "0.1s" }}
                      ></div>
                      <div
                        className="w-2 h-2 bg-gray-400 rounded-full animate-bounce"
                        style={{ animationDelay: "0.2s" }}
                      ></div>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          )}
          <div ref={messagesEndRef} />
        </div>

        {/* Document Upload Section */}
        {selectedFiles.length > 0 && (
          <div className="px-6 py-3 border-t border-gray-100">
            <div className="bg-blue-50 rounded-2xl p-4">
              <div className="flex items-center justify-between mb-3">
                <h3 className="text-sm font-medium text-blue-900">
                  Selected Documents
                </h3>
                <div className="flex space-x-2">
                  <button
                    onClick={uploadDocuments}
                    disabled={uploadingDocs}
                    className="px-3 py-1 bg-blue-600 text-white text-xs rounded-lg hover:bg-blue-700 transition-colors disabled:opacity-50"
                  >
                    {uploadingDocs ? "Uploading..." : "Upload"}
                  </button>
                  <button
                    onClick={clearDocuments}
                    className="px-3 py-1 bg-gray-200 text-gray-700 text-xs rounded-lg hover:bg-gray-300 transition-colors"
                  >
                    Clear
                  </button>
                </div>
              </div>
              <div className="space-y-2">
                {selectedFiles.map((file, index) => (
                  <div
                    key={index}
                    className="flex items-center justify-between bg-white rounded-lg p-2"
                  >
                    <div className="flex items-center space-x-3">
                      {getFileIcon(file.name)}
                      <div className="flex-1 min-w-0">
                        <p className="text-sm font-medium text-gray-700 truncate">
                          {file.name}
                        </p>
                        <p className="text-xs text-gray-500">
                          {(file.size / 1024).toFixed(1)} KB
                        </p>
                      </div>
                    </div>
                    <button
                      onClick={() => removeDocument(index)}
                      className="p-1 text-gray-400 hover:text-red-600 transition-colors"
                    >
                      <svg
                        className="w-4 h-4"
                        fill="none"
                        stroke="currentColor"
                        viewBox="0 0 24 24"
                      >
                        <path
                          strokeLinecap="round"
                          strokeLinejoin="round"
                          strokeWidth={2}
                          d="M6 18L18 6M6 6l12 12"
                        />
                      </svg>
                    </button>
                  </div>
                ))}
              </div>
            </div>
          </div>
        )}

        {/* Image Preview */}
        {imagePreview && (
          <div className="px-6 py-3 border-t border-gray-100">
            <div className="flex items-center space-x-3 p-3 bg-gray-50 rounded-2xl">
              <img
                src={imagePreview}
                alt="Selected image"
                className="w-12 h-12 object-cover rounded-xl"
              />
              <div className="flex-1">
                <p className="text-sm font-medium text-gray-700">
                  Image attached
                </p>
                <p className="text-xs text-gray-500">Ready to send</p>
              </div>
              <button
                onClick={removeImage}
                className="p-1 text-gray-400 hover:text-gray-600 transition-colors"
              >
                <svg
                  className="w-4 h-4"
                  fill="none"
                  stroke="currentColor"
                  viewBox="0 0 24 24"
                >
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth={2}
                    d="M6 18L18 6M6 6l12 12"
                  />
                </svg>
              </button>
            </div>
          </div>
        )}

        {/* Input Area */}
        <div className="px-6 py-2 border-t border-gray-300">
          <div className="relative">
            <textarea
              className="w-full pr-32 pl-12 pt-5 bg-gray-100 border-0 rounded-2xl focus:outline-none focus:ring-0 resize-none placeholder-gray-400 text-sm"
              placeholder="Ask me anything"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.shiftKey) {
                  e.preventDefault();
                  sendMessage();
                }
              }}
              rows={1}
              style={{ minHeight: "56px" }}
            />

            {/* Left side buttons */}
            <div className="absolute left-3 top-1/2 transform -translate-y-1/2 flex items-center space-x-1">
              <button
                onClick={() => fileInputRef.current?.click()}
                className="p-2 text-gray-400 hover:text-gray-600 transition-colors rounded-lg"
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
                    d="M4 16l4.586-4.586a2 2 0 012.828 0L16 16m-2-2l1.586-1.586a2 2 0 012.828 0L20 14m-6-6h.01M6 20h12a2 2 0 002-2V6a2 2 0 00-2-2H6a2 2 0 00-2 2v12a2 2 0 002 2z"
                  />
                </svg>
              </button>
            </div>

            {/* Right side buttons */}
            <div className="absolute right-3 top-1/2 transform -translate-y-1/2 flex items-center space-x-2">
              <button
                onClick={recording ? stopRecording : startRecording}
                className={`p-2 transition-colors rounded-lg ${
                  recording
                    ? "text-red-500 hover:text-red-600"
                    : "text-gray-400 hover:text-gray-600"
                }`}
                title={recording ? "Stop Recording" : "Voice Input"}
              >
                {recording ? (
                  <svg
                    className="w-5 h-5 animate-pulse"
                    fill="currentColor"
                    viewBox="0 0 20 20"
                  >
                    <path
                      fillRule="evenodd"
                      d="M10 18a8 8 0 100-16 8 8 0 000 16zM8 7a2 2 0 114 0v4a2 2 0 11-4 0V7z"
                      clipRule="evenodd"
                    />
                  </svg>
                ) : (
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
                      d="M19 11a7 7 0 01-7 7m0 0a7 7 0 01-7-7m7 7v4m0 0H8m4 0h4m-4-8a3 3 0 01-3-3V5a3 3 0 116 0v6a3 3 0 01-3 3z"
                    />
                  </svg>
                )}
              </button>
              <button
                onClick={sendMessage}
                disabled={loading || (!input.trim() && !selectedImage)}
                className={`p-2 rounded-lg transition-colors ${
                  loading || (!input.trim() && !selectedImage)
                    ? "text-gray-300 cursor-not-allowed"
                    : "text-gray-600 hover:text-gray-800"
                }`}
                title="Send"
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
                    d="M12 19l9 2-9-18-9 18 9-2zm0 0v-8"
                  />
                </svg>
              </button>
            </div>

            <input
              type="file"
              ref={fileInputRef}
              onChange={handleImageSelect}
              accept="image/*"
              className="hidden"
            />
            <input
              type="file"
              ref={docInputRef}
              onChange={handleDocumentSelect}
              accept=".pdf,.docx,.json"
              multiple
              className="hidden"
            />
          </div>

          {recording && (
            <div className="mt-3 text-center">
              <div className="inline-flex items-center space-x-2 text-red-500 text-xs">
                <div className="w-2 h-2 bg-red-500 rounded-full animate-pulse"></div>
                <span>Recording... Click mic to stop</span>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

export default ChatBotFinal;
