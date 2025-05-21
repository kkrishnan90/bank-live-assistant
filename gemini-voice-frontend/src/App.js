import React, { useState, useEffect, useRef, useCallback } from 'react';
import './App.css';
import { FontAwesomeIcon } from '@fortawesome/react-fontawesome';
import {
  faMicrophone, faPause, faStop, faPaperPlane // faEraser removed as Clear Console button is removed
} from '@fortawesome/free-solid-svg-icons';

// Constants
const INPUT_SAMPLE_RATE = 16000;  // For microphone input to Gemini (Native 16kHz)
const OUTPUT_SAMPLE_RATE = 24000; // For Gemini's audio output (24kHz)
const MIC_BUFFER_SIZE = 4096;  // Buffer size for ScriptProcessorNode

// Language Constants
const LANGUAGES = [
  { code: 'en-US', name: 'English' },
  { code: 'th-TH', name: 'Thai' },
  { code: 'id-ID', name: 'Indonesian' },
];

// Utility to generate unique IDs (stable, defined outside component)
const generateUniqueId = () => `${Date.now().toString(36)}-${Math.random().toString(36).substring(2, 7)}`;

const App = () => {
  // --- Existing State & Refs (adapted) ---
  const [isRecording, setIsRecording] = useState(false); // Is microphone actively sending audio to Gemini
  const [messages, setMessages] = useState([]); // Stores log entries: { id, type, content, timestamp }
  const [textInputValue, setTextInputValue] = useState(''); // For the text input field
  const [transcriptionMessages, setTranscriptionMessages] = useState([]); // Stores transcription messages: { id, sender, text, is_final }
  const [isLoading, setIsLoading] = useState(false); // Tracks loading state for API calls
  const [selectedLanguage, setSelectedLanguage] = useState(LANGUAGES[0].code); // Default to English
  
  const [bigQueryLogs, setBigQueryLogs] = useState([]); // Stores BigQuery log entries

  const isRecordingRef = useRef(isRecording);
  // isMutedRef removed

  const playbackAudioContextRef = useRef(null); // For playing Gemini's audio
  const localAudioContextRef = useRef(null);    // For processing microphone audio
  const mediaStreamRef = useRef(null);          // Holds the MediaStream from getUserMedia
  const scriptProcessorNodeRef = useRef(null);  // For microphone audio processing
  const audioChunkSentCountRef = useRef(0);     // For throttled logging

  const socketRef = useRef(null);
  const audioQueueRef = useRef([]);             // Queue for Gemini's audio chunks
  const isPlayingRef = useRef(false);           // To manage playback state of Gemini's audio
  const currentAudioSourceRef = useRef(null);   // Ref for the currently playing AudioBufferSourceNode
  const logsAreaRef = useRef(null); // Ref for the logs area to scroll
  const chatAreaRef = useRef(null); // Ref for the chat area to scroll
 
  // Keep refs in sync with state
  useEffect(() => { isRecordingRef.current = isRecording; }, [isRecording]);
  // useEffect for isMutedRef removed

  // --- Log Entry Management ---
  const addLogEntry = useCallback((type, content) => {
    // console.log(`[LOG_ENTRY] Type: ${type}, Content: ${content}`); // This is the general log entry point

    // Filter out GEMINI_AUDIO and MIC_CONTROL messages from being added to the 'messages' state,
    // which populates the UI's "Conversations" panel.
    if (type === 'gemini_audio' || type === 'mic_control') {
      // These messages will still be logged to the browser console if their respective
      // console.log statements are uncommented elsewhere, but they won't appear in the UI panel.
      // console.log(`[UI_PANEL_FILTERED] Type: ${type}, Content: "${content}"`); // For debugging this filter
      return; // Do not add this entry to the 'messages' state for the UI panel
    }

    const newEntry = {
      id: generateUniqueId(),
      type: type, // e.g., 'status', 'ws', 'mic', 'gemini', 'error', 'user'
      content: content,
      timestamp: new Date().toLocaleTimeString()
    };
    setMessages(prevMessages => {
      const updatedMessages = [...prevMessages, newEntry];
      // Optional: Limit number of messages
      // if (updatedMessages.length > 200) {
      //   return updatedMessages.slice(updatedMessages.length - 200);
      // }
      return updatedMessages;
    });
  }, []);

  // --- Fetch BigQuery Logs ---
  const fetchBigQueryLogs = useCallback(async () => {
    setIsLoading(true);
    try {
      const response = await fetch('https://gemini-backend-service-1018963165306.us-central1.run.app/api/logs');
      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }
      const data = await response.json();
      // Assuming data is an array of log objects like: [{ timestamp, message, ...otherFields }]
      // Or if it's just an array of strings: ["log1", "log2"]
      // For now, let's assume it's an array of objects with at least a 'message' field.
      // And ideally a 'timestamp' field.

      const newLogEntries = data.map(log => ({
        id: generateUniqueId(),
        type: 'bigquery', // Differentiate BigQuery logs
        // Use log.message or log.text or JSON.stringify(log) if structure is unknown/complex
        content: typeof log === 'string' ? log : log.message || JSON.stringify(log),
        timestamp: log.timestamp ? new Date(log.timestamp).toLocaleTimeString() : new Date().toLocaleTimeString()
      }));
// START MODIFICATION: Log BigQuery entries to console with specific colors
      newLogEntries.forEach(logEntry => {
        // Ensure content is a string before calling toLowerCase
        const logContentString = String(logEntry.content);
        const contentLowerCase = logContentString.toLowerCase();
        const errorKeywords = ['error', 'failed', 'exception', 'traceback', 'critical', 'err:', 'warn:', 'warning'];
        let isError = false;

        // Check for error status (if exists on logEntry from backend) or keywords in content
        if (logEntry.status && String(logEntry.status).toLowerCase().includes('error')) {
            isError = true;
        } else {
            isError = errorKeywords.some(keyword => contentLowerCase.includes(keyword));
        }

        if (isError) {
          console.log(`%c[BigQuery ERROR] ${logEntry.timestamp}: ${logContentString}`, 'color: #FF3131; font-weight: bold;'); // Neon Red
        } else {
          console.log(`%c[BigQuery Log] ${logEntry.timestamp}: ${logContentString}`, 'color: #39FF14;'); // Neon Green
        }
      });
      // END MODIFICATION

      // Add to general messages for display, ensuring no duplicates if logs are fetched repeatedly
      // A more robust deduplication might be needed if logs don't have unique IDs from backend
      setMessages(prevMessages => {
        const existingLogContents = new Set(prevMessages.filter(m => m.type === 'bigquery').map(m => m.content));
        const uniqueNewEntries = newLogEntries.filter(newLog => !existingLogContents.has(newLog.content));
        return [...prevMessages, ...uniqueNewEntries].sort((a, b) => new Date('1970/01/01 ' + a.timestamp) - new Date('1970/01/01 ' + b.timestamp));
      });
      setBigQueryLogs(prevLogs => [...prevLogs, ...newLogEntries]); // Keep a separate state if needed for other purposes

    } catch (error) {
      console.error("Failed to fetch BigQuery logs:", error);
      addLogEntry('error', `Failed to fetch BigQuery logs: ${error.message}`);
    } finally {
      setIsLoading(false);
    }
  }, [addLogEntry]); // addLogEntry is a dependency

  // Periodically fetch BigQuery logs
  useEffect(() => {
    fetchBigQueryLogs(); // Fetch on initial load
    const intervalId = setInterval(fetchBigQueryLogs, 15000); // Fetch every 15 seconds

    return () => clearInterval(intervalId); // Cleanup interval on component unmount
  }, [fetchBigQueryLogs]);

  // Auto-scroll logs area
  useEffect(() => {
    if (logsAreaRef.current) {
      logsAreaRef.current.scrollTop = logsAreaRef.current.scrollHeight;
    }
  }, [messages]);
 
  // Auto-scroll chat area
  useEffect(() => {
    if (chatAreaRef.current) {
      chatAreaRef.current.scrollTop = chatAreaRef.current.scrollHeight;
    }
  }, [transcriptionMessages]);

  useEffect(() => {
    // console.log('DEBUG: transcriptionMessages state CHANGED:', transcriptionMessages);
  }, [transcriptionMessages]);
  
  // --- AudioContext Management (Playback) - Largely unchanged ---
  const getPlaybackAudioContext = useCallback(async (triggeredByAction) => {
    // console.log(`[CTX_PLAYBACK_MGR] getPlaybackAudioContext called by: ${triggeredByAction}`);
    if (!playbackAudioContextRef.current) {
      try {
        addLogEntry('audio', 'Attempting to create Playback AudioContext.');
        playbackAudioContextRef.current = new (window.AudioContext || window.webkitAudioContext)({
          sampleRate: OUTPUT_SAMPLE_RATE,
        });
        playbackAudioContextRef.current.onstatechange = () => {
          const newState = playbackAudioContextRef.current?.state;
          addLogEntry('audio', `PlaybackCTX state changed to: ${newState}`);
        };
        const initialState = playbackAudioContextRef.current.state;
        addLogEntry('audio', `Playback AudioContext CREATED. Initial state: ${initialState}, SampleRate: ${playbackAudioContextRef.current.sampleRate}`);
      } catch (e) {
        console.error('[CTX_PLAYBACK_MGR] !!! FAILED to CREATE Playback AudioContext !!!', e);
        addLogEntry('error', `FATAL PlaybackCTX ERROR: ${e.message}`);
        playbackAudioContextRef.current = null; return null;
      }
    }
    if (playbackAudioContextRef.current.state === 'suspended') {
      if (triggeredByAction && (triggeredByAction.toLowerCase().includes("user_action") || triggeredByAction.toLowerCase().includes("systemaction"))) {
        addLogEntry('audio', `PlaybackCTX State 'suspended'. Attempting RESUME by: ${triggeredByAction}.`);
        try {
          await playbackAudioContextRef.current.resume();
          addLogEntry('audio', `PlaybackCTX Resume attempt finished. State: ${playbackAudioContextRef.current.state}`);
        } catch (e) {
          console.error(`[CTX_PLAYBACK_MGR] !!! FAILED to RESUME PlaybackCTX !!!`, e);
          addLogEntry('error', `FAILED to RESUME PlaybackCTX: ${e.message}`);
        }
      }
    }
    const finalState = playbackAudioContextRef.current?.state;
    if (finalState !== 'running') addLogEntry('warning', `PlaybackCTX not 'running'. State: ${finalState}`);
    return playbackAudioContextRef.current;
  }, [addLogEntry]);

  // --- Play Gemini's Audio Response - Largely unchanged, uses addLogEntry ---
  const playNextGeminiChunk = useCallback(async () => {
    if (isPlayingRef.current || audioQueueRef.current.length === 0) return;
    isPlayingRef.current = true;
    const arrayBuffer = audioQueueRef.current.shift();

    const audioCtx = await getPlaybackAudioContext("playNextGeminiChunk_SystemAction");
    if (!audioCtx || audioCtx.state !== 'running') {
      console.error(`[GEMINI_PLAY] Cannot play: PlaybackCTX not 'running'. State: ${audioCtx?.state}`);
      addLogEntry('error', `Playback FAIL: Audio system not ready (${audioCtx?.state})`);
      isPlayingRef.current = false; return;
    }
    try {
      if (arrayBuffer.byteLength === 0 || arrayBuffer.byteLength % 2 !== 0) {
        console.error("[GEMINI_PLAY] Invalid ArrayBuffer (0 bytes or odd length). Skipping.", arrayBuffer.byteLength);
        addLogEntry('warning', 'Received empty or invalid audio chunk from Gemini. Skipping playback.');
        isPlayingRef.current = false; playNextGeminiChunk(); return;
      }
      const pcm16Data = new Int16Array(arrayBuffer);
      const float32Data = new Float32Array(pcm16Data.length);
      for (let i = 0; i < pcm16Data.length; i++) float32Data[i] = pcm16Data[i] / 32768.0;
      
      if (float32Data.length === 0) { 
        addLogEntry('warning', 'Received empty audio chunk (after conversion) from Gemini. Skipping playback.');
        isPlayingRef.current = false; playNextGeminiChunk(); return;
      }
      
      const audioBuffer = audioCtx.createBuffer(1, float32Data.length, OUTPUT_SAMPLE_RATE);
      audioBuffer.copyToChannel(float32Data, 0);
      const source = audioCtx.createBufferSource();
      source.buffer = audioBuffer;
      const gainNode = audioCtx.createGain();
      gainNode.gain.setValueAtTime(0.8, audioCtx.currentTime); 
      source.connect(gainNode);
      gainNode.connect(audioCtx.destination);
      source.onended = () => {
        addLogEntry('gemini_audio', 'Audio chunk finished playing.');
        isPlayingRef.current = false;
        currentAudioSourceRef.current = null; 
        playNextGeminiChunk();
        source.disconnect(); gainNode.disconnect();
      };
      currentAudioSourceRef.current = source; 
      addLogEntry('gemini_audio', 'Starting playback of Gemini audio chunk...');
      source.start();
    } catch (error) {
        currentAudioSourceRef.current = null; 
        console.error("!!! [GEMINI_PLAY] Error in playNextGeminiChunk !!!", error);
        addLogEntry('error', `Playback Error: ${error.message}`);
        isPlayingRef.current = false;
        playNextGeminiChunk();
    }
  }, [getPlaybackAudioContext, addLogEntry]);

  const stopSystemAudioPlayback = useCallback(() => {
    if (currentAudioSourceRef.current) {
      try {
        currentAudioSourceRef.current.stop();
        // The onended event of the source will handle cleanup like setting currentAudioSourceRef.current to null
        addLogEntry('gemini_audio', 'System audio playback stopped by barge-in.');
      } catch (e) {
        addLogEntry('warning', `Could not stop current audio source for barge-in: ${e.message}`);
        // Ensure cleanup if stop() fails or source was already gone
        currentAudioSourceRef.current = null;
      }
    }
    audioQueueRef.current = []; // Clear any pending audio chunks
    isPlayingRef.current = false; // Mark as not playing
    addLogEntry('gemini_audio', 'Gemini audio queue cleared due to barge-in.');
  }, [addLogEntry]); // currentAudioSourceRef, audioQueueRef, isPlayingRef are refs, not needed in deps

  // --- WebSocket Connection - Uses addLogEntry ---
  const connectWebSocket = useCallback((language) => {
    if (socketRef.current && (socketRef.current.readyState === WebSocket.OPEN || socketRef.current.readyState === WebSocket.CONNECTING)) {
      // If trying to connect with the same language and already open/connecting, do nothing.
      if (socketRef.current.url.includes(`lang=${language}`)) {
        addLogEntry('ws', `WebSocket already open or connecting with ${language}. Aborting new connection.`);
        return;
      }
      // If language is different, the useEffect should have closed it.
      addLogEntry('ws', `WebSocket open/connecting, but language mismatch. Expected ${language}. Current URL: ${socketRef.current.url}. Proceeding to close and reconnect.`);
      socketRef.current.close(1000, 'Language changed by user - pre-emptive close'); // Close it before creating new
    }
    addLogEntry('ws', `Connecting to WebSocket with language: ${language}...`);
    socketRef.current = new WebSocket(`ws://gemini-backend-service-1018963165306.us-central1.run.app/listen?lang=${language}`);
    socketRef.current.binaryType = 'arraybuffer';

    socketRef.current.onopen = () => {
      addLogEntry('ws', `WebSocket Connected (Lang: ${language}).`);
      setIsRecording(true); // Auto-start recording on successful connection
    };
    socketRef.current.onmessage = (event) => {
      if (typeof event.data === 'string') {
        try {
          const receivedData = JSON.parse(event.data);
          // console.log('Full JSON message received from backend:', receivedData);

          if (receivedData.type && receivedData.type.endsWith('_update')) {
            addLogEntry(receivedData.type, `${receivedData.sender}: ${receivedData.text} (Final: ${receivedData.is_final})`);
            setTranscriptionMessages(prevMessages => {
              const existingMessageIndex = prevMessages.findIndex(msg => msg.id === receivedData.id);
              if (existingMessageIndex !== -1) {
                // Update existing message
                return prevMessages.map(msg =>
                  msg.id === receivedData.id
                    ? { ...msg, text: receivedData.text, is_final: receivedData.is_final }
                    : msg
                );
              } else {
                // Add new message
                return [
                  ...prevMessages,
                  { id: receivedData.id, text: receivedData.text, sender: receivedData.sender, is_final: receivedData.is_final }
                ];
              }
            });
          }
          // Fallback for older message types or non-update messages
          else if (receivedData.type === 'user_transcription' && receivedData.sender === 'user') { // DEPRECATED by user_transcription_update
            const newMessageObject = { id: receivedData.id || generateUniqueId(), text: receivedData.text, sender: 'user', is_final: receivedData.is_final !== undefined ? receivedData.is_final : true };
            addLogEntry('user_transcription_fallback', `User (fallback): ${receivedData.text}`);
            setTranscriptionMessages(prev => [...prev, newMessageObject]);
          } else if (receivedData.type === 'model_response' && receivedData.sender === 'model') { // DEPRECATED by model_response_update
            const newMessageObject = { id: receivedData.id || generateUniqueId(), text: receivedData.text, sender: 'model', is_final: receivedData.is_final !== undefined ? receivedData.is_final : true };
            addLogEntry('model_response_fallback', `Model (fallback): ${receivedData.text}`);
            setTranscriptionMessages(prev => [...prev, newMessageObject]);
          } else if (receivedData.transcriptionText) {
           addLogEntry('transcription_live', `Live Transcription (old): ${receivedData.transcriptionText}`);
           const newTranscription = { id: generateUniqueId(), sender: 'user', text: receivedData.transcriptionText, is_final: true };
           setTranscriptionMessages(prev => {
             if (!prev.find(msg => msg.text === newTranscription.text && msg.sender === 'user')) {
               return [...prev, newTranscription];
             }
             return prev;
           });
         } else if (receivedData.type === 'gemini_response') {
            addLogEntry('gemini_text', `Gemini (deprecated): ${receivedData.text}`);
            const aiMessage = { id: generateUniqueId(), sender: 'ai', text: receivedData.text, is_final: true };
            setTranscriptionMessages(prev => [...prev, aiMessage]);
          } else if (receivedData.type === 'aiResponse') {
            addLogEntry('ai_response', `AI (fallback): ${receivedData.text}`);
            const aiMessage = { id: generateUniqueId(), sender: 'ai', text: receivedData.text, is_final: true };
            setTranscriptionMessages(prev => [...prev, aiMessage]);
          } else if (receivedData.type === 'transcription' && receivedData.sender !== 'user' && receivedData.sender !== 'model') {
            addLogEntry('transcription', `Transcription (fallback ${receivedData.sender || 'unknown'}): ${receivedData.text}`);
            const userMessage = { id: generateUniqueId(), sender: receivedData.sender || 'user', text: receivedData.text, is_final: true };
            setTranscriptionMessages(prev => [...prev, userMessage]);
          } else if (receivedData.type === 'interim_transcript') { // This is likely from a different system, but good to log
            addLogEntry('user_speech_interim_old', `You (interim old): ${receivedData.transcript}`);
          } else if (receivedData.type === 'final_transcript') { // This is likely from a different system
            addLogEntry('user_speech_final_old', `You (final old): ${receivedData.transcript}`);
          } else if (receivedData.type === 'error') {
            addLogEntry('error', `Server Error: ${receivedData.message}`);
          } else {
            addLogEntry('ws_json_unhandled', `Unhandled JSON structure: ${event.data}`);
          }
        } catch (e) {
          console.error('Error parsing JSON data:', e);
          // console.log('Raw string data that failed to parse:', event.data);
          addLogEntry('error', `Failed to parse JSON: ${e.message}. Raw data: ${event.data.substring(0,100)}...`);
        }
      } else if (event.data instanceof ArrayBuffer) {
        // console.log('Received ArrayBuffer from backend (likely audio data):', event.data);
        // Existing logic for handling ArrayBuffer
        audioQueueRef.current.push(event.data);
        if (!isPlayingRef.current) playNextGeminiChunk();
      } else {
        // console.log('Received unknown data type from backend:', event.data);
        addLogEntry('ws_unknown', `Received unknown data type: ${typeof event.data}`);
      }
    };
    socketRef.current.onerror = (error) => {
      console.error('WebSocket Error:', error);
      addLogEntry('error', 'WebSocket error. See console for details.');
      setIsRecording(false);
    };
    socketRef.current.onclose = (event) => {
      addLogEntry('ws', `WebSocket Disconnected. Code: ${event.code}, Reason: "${event.reason || 'No reason given'}"`);
      setIsRecording(false); // Ensure recording state is updated
      
      // Specific handling for language change or unmount closures
      if (event.reason === 'Language changed by user' || event.reason === 'Component unmounting' || event.reason === 'Component unmounting or language changing again' || event.reason === 'Language changed by user - pre-emptive close') {
        addLogEntry('ws', `WebSocket closed intentionally (${event.reason}). No automatic reconnection.`);
      } else if (event.code !== 1000 && event.code !== 1005) { // 1000 normal, 1005 no status
        addLogEntry('error', `WebSocket closed unexpectedly. Code: ${event.code}. Consider manual reconnect.`);
      }
    };
  }, [addLogEntry, playNextGeminiChunk]); // selectedLanguage is not needed here as it's passed as 'language' parameter

  // Effect to manage WebSocket connection based on selected language
  useEffect(() => {
    const currentLangName = LANGUAGES.find(l => l.code === selectedLanguage)?.name || selectedLanguage;
    addLogEntry('system', `Language selected: ${currentLangName} (${selectedLanguage}). Managing WebSocket connection.`);

    if (socketRef.current && (socketRef.current.readyState === WebSocket.OPEN || socketRef.current.readyState === WebSocket.CONNECTING)) {
      if (!socketRef.current.url.includes(`lang=${selectedLanguage}`)) {
        addLogEntry('ws', `Language or URL mismatch. Closing existing WebSocket (state: ${socketRef.current.readyState}) for ${socketRef.current.url}`);
        socketRef.current.close(1000, 'Language changed by user');
        // Set a timeout to establish new connection after the old one has had a chance to close
        const timeoutId = setTimeout(() => {
          addLogEntry('ws', `Attempting to connect with new language: ${currentLangName} (${selectedLanguage}) after old socket closure initiated.`);
          connectWebSocket(selectedLanguage);
        }, 150); // Adjusted delay
        return () => clearTimeout(timeoutId);
      } else {
         addLogEntry('ws', `WebSocket already connected with ${currentLangName} (${selectedLanguage}). No change needed.`);
         return; // Already connected with the correct language
      }
    } else {
      // No open/connecting socket, or socket exists but is closed/closing. Attempt to connect.
      addLogEntry('ws', `No active WebSocket or mismatch. Connecting with language: ${currentLangName} (${selectedLanguage}).`);
      connectWebSocket(selectedLanguage);
    }
    
    return () => {
      if (socketRef.current && 
          (socketRef.current.readyState === WebSocket.OPEN || socketRef.current.readyState === WebSocket.CONNECTING) &&
          socketRef.current.url.includes(`lang=${selectedLanguage}`)) { 
        addLogEntry('ws', `Effect cleanup for ${currentLangName} (${selectedLanguage}): Closing WebSocket.`);
        socketRef.current.close(1000, 'Component unmounting or language changing again');
      }
    };
  }, [selectedLanguage, connectWebSocket, addLogEntry]);


  // --- Microphone Audio Processing - Uses addLogEntry ---
  const processAudio = useCallback((audioProcessingEvent) => {
    // isMutedRef.current check removed
    if (!isRecordingRef.current || !socketRef.current || socketRef.current.readyState !== WebSocket.OPEN) {
      return;
    }

    // Barge-in detection: If system is playing audio and mic picks up new audio
    if (isPlayingRef.current) {
      // A simple check for any audio activity. More sophisticated VAD could be added.
      const inputData = audioProcessingEvent.inputBuffer.getChannelData(0);
      // Basic check if there's any significant audio, avoiding tiny noise triggering barge-in.
      // This threshold is arbitrary and might need tuning.
      const hasAudioSignal = inputData.some(sample => Math.abs(sample) > 0.04); // Increased threshold for barge-in to reduce sensitivity

      if (hasAudioSignal) {
        addLogEntry('barge_in', 'User speech detected during system playback. Initiating barge-in.');
        stopSystemAudioPlayback();
        // System audio is now stopping/stopped. Continue to process this user audio chunk.
      }
    }

    const inputBuffer = audioProcessingEvent.inputBuffer;
    const pcmData = inputBuffer.getChannelData(0);
    const downsampledBuffer = new Int16Array(pcmData.length);
    for (let i = 0; i < pcmData.length; i++) {
      downsampledBuffer[i] = Math.max(-1, Math.min(1, pcmData[i])) * 32767;
    }
    if (socketRef.current && socketRef.current.readyState === WebSocket.OPEN) {
      socketRef.current.send(downsampledBuffer.buffer);
      audioChunkSentCountRef.current++;
      if (audioChunkSentCountRef.current % 100 === 0) { // Log every 100 chunks
        // addLogEntry('mic', `Sent ${audioChunkSentCountRef.current} audio chunks.`);
      }
    }
  }, [addLogEntry, stopSystemAudioPlayback]); // Added stopSystemAudioPlayback to dependencies
 
  // --- Start Listening (Microphone & WebSocket) ---
  const handleStartListening = useCallback(async () => {
    if (isRecording) {
      addLogEntry('mic_control', 'Already listening. Request to start ignored.');
      return;
    }
    addLogEntry('mic_control', 'Start Listening requested by user.');
    await getPlaybackAudioContext("handleStartListening_UserAction"); // Ensure playback context is ready & resumed

    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
      addLogEntry('error', 'getUserMedia not supported on your browser!');
      return;
    }
    try {
      addLogEntry('mic', 'Requesting microphone access...');
      mediaStreamRef.current = await navigator.mediaDevices.getUserMedia({ audio: { sampleRate: INPUT_SAMPLE_RATE, channelCount: 1 } });
      addLogEntry('mic', 'Microphone access GRANTED.');
      
      localAudioContextRef.current = new (window.AudioContext || window.webkitAudioContext)({ sampleRate: INPUT_SAMPLE_RATE });
      const source = localAudioContextRef.current.createMediaStreamSource(mediaStreamRef.current);
      scriptProcessorNodeRef.current = localAudioContextRef.current.createScriptProcessor(MIC_BUFFER_SIZE, 1, 1);
      scriptProcessorNodeRef.current.onaudioprocess = processAudio;
      source.connect(scriptProcessorNodeRef.current);
      scriptProcessorNodeRef.current.connect(localAudioContextRef.current.destination); // Connect to destination to start processing

      // connectWebSocket is now primarily handled by the useEffect for selectedLanguage.
      // However, if the socket is not open and we click start, we should ensure it tries to connect with the current language.
      if (!socketRef.current || socketRef.current.readyState !== WebSocket.OPEN) {
        const currentLangName = LANGUAGES.find(l => l.code === selectedLanguage)?.name || selectedLanguage;
        addLogEntry('ws', `Start Listening: WebSocket not open. Attempting connection with ${currentLangName} (${selectedLanguage}).`);
        connectWebSocket(selectedLanguage);
      } else {
         // If socket is already open, ensure it's for the correct language.
         // The useEffect for selectedLanguage should handle mismatches, but this is a safeguard.
        if (!socketRef.current.url.includes(`lang=${selectedLanguage}`)) {
          const currentLangName = LANGUAGES.find(l => l.code === selectedLanguage)?.name || selectedLanguage;
          addLogEntry('ws', `Start Listening: WebSocket open but language mismatch. Re-initiating connection for ${currentLangName} (${selectedLanguage}).`);
          socketRef.current.close(1000, 'Language mismatch on start listening');
          // Delay to allow close then reconnect via useEffect
          setTimeout(() => connectWebSocket(selectedLanguage), 150);
        } else {
          setIsRecording(true); // If already open with correct language, just set recording.
        }
      }
      // setIsRecording(true); // This is now mostly handled by socket onopen or above logic.

    } catch (err) {
      console.error('Error accessing microphone or setting up audio processing:', err);
      addLogEntry('error', `Microphone Error: ${err.message}. Please check permissions.`);
      setIsRecording(false);
    }
  }, [isRecording, processAudio, connectWebSocket, addLogEntry, getPlaybackAudioContext, selectedLanguage]);

  // --- Stop Listening (Pauses sending audio to Gemini, keeps WS open) ---
  const handlePauseListening = useCallback(() => {
    if (!isRecording) {
      addLogEntry('mic_control', 'Not currently listening. Request to pause ignored.');
      return;
    }
    addLogEntry('mic_control', 'Pause Listening requested by user.');
    setIsRecording(false);
    // Note: This doesn't close the WebSocket, just stops sending mic data.
    // It also doesn't stop the microphone hardware itself yet, processAudio simply returns.
    // To fully release mic, we'd need to stop tracks and disconnect nodes in handleHardStop.
  }, [isRecording, addLogEntry]);

  // --- Hard Stop (Stops Mic, Closes WS, Clears Audio Queue) ---
  const handleHardStop = useCallback(() => {
    addLogEntry('session_control', 'Stop Session requested by user.');
    setIsRecording(false);
    // setIsMuted(false) removed

    // Stop microphone input processing and release hardware
    if (scriptProcessorNodeRef.current) {
      scriptProcessorNodeRef.current.disconnect();
      scriptProcessorNodeRef.current.onaudioprocess = null; // Remove listener
      scriptProcessorNodeRef.current = null;
      addLogEntry('mic', 'ScriptProcessorNode disconnected.');
    }
    if (mediaStreamRef.current) {
      mediaStreamRef.current.getTracks().forEach(track => track.stop());
      mediaStreamRef.current = null;
      addLogEntry('mic', 'MediaStream tracks stopped.');
    }
    if (localAudioContextRef.current && localAudioContextRef.current.state !== 'closed') {
      localAudioContextRef.current.close().then(() => addLogEntry('mic', 'Local AudioContext closed.'));
      localAudioContextRef.current = null;
    }

    // Close WebSocket connection
    if (socketRef.current) {
      if (socketRef.current.readyState === WebSocket.OPEN || socketRef.current.readyState === WebSocket.CONNECTING) {
        socketRef.current.close(1000, 'User requested session stop.');
      }
      socketRef.current = null; // Explicitly nullify after attempting close
      addLogEntry('ws', 'WebSocket connection explicitly closed by user.');
    }

    // Stop any ongoing playback and clear queue
    if (currentAudioSourceRef.current) {
      try {
        currentAudioSourceRef.current.stop();
        addLogEntry('gemini_audio', 'Ongoing Gemini audio playback stopped.');
      } catch (e) {
        addLogEntry('warning', 'Could not stop current audio source (already stopped or invalid state).');
      }
      currentAudioSourceRef.current = null;
    }
    audioQueueRef.current = [];
    isPlayingRef.current = false;
    addLogEntry('gemini_audio', 'Gemini audio queue cleared.');

    // Optionally close playback audio context if not needed further, or keep for future use
    // if (playbackAudioContextRef.current && playbackAudioContextRef.current.state !== 'closed') {
    //   playbackAudioContextRef.current.close().then(() => addLogEntry('audio', 'Playback AudioContext closed.'));
    //   playbackAudioContextRef.current = null;
    // }

    addLogEntry('session_control', 'Session stopped and resources released.');

  }, [addLogEntry]);

  // --- Toggle Mute --- (REMOVED)
  // const handleToggleMute = useCallback(() => {
  //   setIsMuted(prevMuted => {
  //     const newMuteState = !prevMuted;
  //     addLogEntry('mic_control', `Microphone ${newMuteState ? 'MUTED' : 'UNMUTED'}.`);
  //     return newMuteState;
  //   });
  // }, [addLogEntry]);

  // --- Send Text Message ---
  const handleSendTextMessage = useCallback(() => {
    if (!textInputValue.trim()) return;
    
    const currentLangName = LANGUAGES.find(l => l.code === selectedLanguage)?.name || selectedLanguage;
    addLogEntry('user_text', `User typed (Lang: ${currentLangName}): "${textInputValue}"`);

    if (socketRef.current && socketRef.current.readyState === WebSocket.OPEN) {
      const messagePayload = { 
        type: 'text_message', // Ensure backend expects this type for text
        text: textInputValue,
        language: selectedLanguage, // Add selected language to payload
        timestamp: new Date().toISOString(),
        id: generateUniqueId() 
      };
      socketRef.current.send(JSON.stringify(messagePayload));
      
      // Add to local transcription display as a user message
      setTranscriptionMessages(prev => [
        ...prev,
        {
          id: messagePayload.id, 
          sender: 'user',
          text: textInputValue,
          is_final: true, 
          timestamp: new Date().toLocaleTimeString()
        }
      ]);
      setTextInputValue(''); // Clear input field
    } else {
      addLogEntry('error', 'Cannot send text: WebSocket not connected or not open.');
    }
  }, [textInputValue, addLogEntry, selectedLanguage]);

  const handleClearConsole = () => {
    setMessages([]);
    addLogEntry('console', 'Console cleared by user.');
  };

  // Initial welcome message
  useEffect(() => {
    addLogEntry('status', 'Welcome! Click the microphone to start or type your query.');
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []); // Empty dependency array means this runs once on mount


  return (
    <div className="app-container">
      {/* Console Panel (Left) */}
      <div className="console-panel">
        <div className="console-header">
          <h2>Console</h2>
          <div className="console-header-controls">
            <select className="console-dropdown" defaultValue="conversations">
              <option value="conversations">Conversations</option>
              {/* Add other options here if needed */}
            </select>
            <button className="console-paused-button">Paused</button>
          </div>
        </div>
        <div className="logs-area" ref={logsAreaRef}>
          {isLoading && <p className="loading-indicator">Loading...</p>}
          {messages.map(msg => ( // messages now includes BigQuery logs
            <div key={msg.id} className={`log-entry log-entry-${msg.type} ${msg.type === 'bigquery' ? 'log-entry-bigquery' : ''}`}>
              <span className="log-timestamp">[{msg.timestamp}] </span>
              <span className="log-prefix">{msg.type.toUpperCase()}: </span>
              <span className="log-message">{msg.content}</span>
            </div>
          ))}
        </div>
        <div className="text-input-area console-text-input-area">
          <input
            type="text"
            className="text-input"
            value={textInputValue}
            onChange={(e) => setTextInputValue(e.target.value)}
            onKeyPress={(e) => e.key === 'Enter' && handleSendTextMessage()}
            placeholder="Type something..."
            // disabled={isRecording} // Retaining this logic for now, can be adjusted
          />
          <button onClick={handleSendTextMessage} className="control-button send-button" disabled={!textInputValue.trim()}>
            <FontAwesomeIcon icon={faPaperPlane} />
          </button>
        </div>
      </div>

      {/* Main Panel (Right) */}
      <div className="main-panel">
        <div className="main-panel-header">
          <h2>Transcriptions</h2>
        </div>
        <div className="results-content chat-area" ref={chatAreaRef}>
          {transcriptionMessages.length === 0 && (
            <div className="results-content-placeholder">
              <p>Audio transcriptions will appear here.</p>
            </div>
          )}
          {transcriptionMessages.map(msg => {
            // console.log('DEBUG: Rendering transcription message in JSX:', msg);
            return (
              <div key={msg.id} className={`chat-bubble ${msg.sender === 'user' ? 'user-bubble' : 'ai-bubble'}`}>
                <div className="chat-bubble-text">{msg.text}</div>
              </div>
            );
          })}
        </div>
      </div>
 
      {/* Control Bar (Bottom) */}
      <div className="control-bar">
        <div className="control-tray">
          <button onClick={isRecording ? handlePauseListening : handleStartListening} className={`control-button mic-button ${isRecording ? 'active' : ''}`} title={isRecording ? 'Pause Listening' : 'Start Listening'}>
            <FontAwesomeIcon icon={isRecording ? faPause : faMicrophone} />
          </button>
          <button onClick={handleHardStop} className="control-button stop-button" title="Stop Session">
            <FontAwesomeIcon icon={faStop} />
          </button>
          
          {/* Language Selector in Control Bar */}
          <div className="language-selector-control-bar" style={{ display: 'flex', alignItems: 'center', marginLeft: '12px', marginRight: '10px' }}>
            <label htmlFor="language-select-ctrl" style={{ marginRight: '6px', color: '#c0c0c0', fontSize:'0.8rem', fontWeight: 'normal', whiteSpace: 'nowrap' }}>Language:</label>
            <select
              id="language-select-ctrl"
              value={selectedLanguage}
              onChange={(e) => {
                const newLangCode = e.target.value;
                const newLangName = LANGUAGES.find(l => l.code === newLangCode)?.name || newLangCode;
                addLogEntry('ui_event', `Language changed to: ${newLangName} (${newLangCode})`);
                setSelectedLanguage(newLangCode);
              }}
              style={{ 
                padding: '5px 8px', 
                borderRadius: '4px', 
                border: '1px solid #4a4a4a', 
                backgroundColor: '#252526', 
                color: '#d4d4d4', 
                fontSize:'0.8rem', 
                cursor: 'pointer',
                outline: 'none',
                height: '30px', 
                minWidth: '120px' 
              }}
              title="Select Language"
            >
              {LANGUAGES.map(lang => (
                <option key={lang.code} value={lang.code} style={{backgroundColor: '#252526', color: '#d4d4d4', padding: '5px'}}>
                  {lang.name} ({lang.code})
                </option>
              ))}
            </select>
          </div>

          <div className="audio-signal-placeholder"> 
            {isRecording && (
              <div className="audio-wave">
                <span></span><span></span><span></span><span></span><span></span>
              </div>
            )}
          </div>
          
          {/* Combined Status Indicator in Control Bar */}
          <div className="status-indicator-ctrl-bar" 
               style={{ 
                 marginLeft: 'auto', 
                 marginRight: '10px', 
                 color: '#c0c0c0', 
                 fontSize: '0.75rem', 
                 display: 'flex', 
                 alignItems: 'center',
                 padding: '0 10px', 
                 backgroundColor: '#252526',
                 border: '1px solid #4a4a4a',
                 borderRadius: '4px',
                 height: '30px', 
                 lineHeight: '30px'
               }}>
             MIC:&#160;{isRecording ? 
                  <span style={{color: '#66bb6a', fontWeight:'bold', letterSpacing: '0.5px'}}>ON</span> : 
                  <span style={{color: '#ef5350', fontWeight:'bold', letterSpacing: '0.5px'}}>OFF</span>}
             <span style={{margin: '0 10px', color: '#505050'}}>|</span>
             WS:&#160;{socketRef.current && socketRef.current.readyState === WebSocket.OPEN ? 
                  <span style={{color: '#66bb6a', fontWeight:'bold', letterSpacing: '0.5px'}}>ON ({LANGUAGES.find(l => l.code === selectedLanguage)?.name || selectedLanguage})</span> : 
                  <span style={{color: '#ef5350', fontWeight:'bold', letterSpacing: '0.5px'}}>OFF</span>}
          </div>
        </div>
        {/* Text input area moved to console-panel */}
      </div>
    </div>
  );
};

export default App;
