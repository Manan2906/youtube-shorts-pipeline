"use client";

import { useState, useEffect, useRef } from "react";

const API = "http://localhost:8003";

const NICHE_GROUPS = [
  {
    label: "Job Roles",
    niches: [
      { id: "marketing", name: "Marketing" },
      { id: "hr", name: "HR & People" },
      { id: "sales", name: "Sales" },
      { id: "product", name: "Product Management" },
      { id: "startup", name: "Startups & Founders" },
      { id: "leadership", name: "Leadership & CXO" },
    ],
  },
  {
    label: "Industries",
    niches: [
      { id: "finance", name: "Finance & Markets" },
      { id: "tech", name: "Tech & AI" },
      { id: "science", name: "Science" },
      { id: "education", name: "Education" },
      { id: "politics", name: "Politics" },
    ],
  },
  {
    label: "Lifestyle",
    niches: [
      { id: "fitness", name: "Fitness" },
      { id: "cooking", name: "Cooking" },
      { id: "travel", name: "Travel" },
      { id: "entertainment", name: "Entertainment" },
      { id: "sports", name: "Sports" },
      { id: "fashion", name: "Fashion" },
      { id: "gaming", name: "Gaming" },
      { id: "motivation", name: "Motivation" },
      { id: "comedy", name: "Comedy" },
      { id: "true_crime", name: "True Crime" },
      { id: "general", name: "General" },
    ],
  },
];

const TONES = [
  { value: "", label: "Auto (from niche)" },
  { value: "professional", label: "Professional" },
  { value: "casual", label: "Casual & Friendly" },
  { value: "witty", label: "Witty & Sarcastic" },
  { value: "dramatic", label: "Dramatic & Intense" },
  { value: "educational", label: "Educational & Clear" },
  { value: "inspirational", label: "Inspirational" },
];

const MOODS = [
  { value: "", label: "Auto (from niche)" },
  { value: "serious", label: "Serious" },
  { value: "fun", label: "Fun & Light" },
  { value: "urgent", label: "Urgent & Breaking" },
  { value: "thoughtful", label: "Thoughtful & Deep" },
  { value: "provocative", label: "Provocative & Bold" },
];

const LANGUAGES = [
  { value: "en", label: "English" },
  { value: "hi", label: "Hindi" },
  { value: "es", label: "Spanish" },
  { value: "pt", label: "Portuguese" },
  { value: "de", label: "German" },
  { value: "fr", label: "French" },
  { value: "ja", label: "Japanese" },
  { value: "ko", label: "Korean" },
];

const STAGES = [
  { key: "research", label: "Researching topic", match: ["research", "starting", "initializ"] },
  { key: "script", label: "Writing script", match: ["script", "writing", "drafting"] },
  { key: "clips", label: "Downloading video clips", match: ["download", "pexels", "clip", "video clips"] },
  { key: "voice", label: "Generating voiceover", match: ["voice", "tts", "voiceover"] },
  { key: "captions", label: "Creating captions", match: ["caption", "whisper"] },
  { key: "assemble", label: "Assembling video", match: ["assembl", "trimming", "final"] },
];

type JobStatus = {
  status: string;
  stage: string;
  progress: number;
  draft: Record<string, unknown> | null;
  video_path: string | null;
  error: string | null;
};

export default function Home() {
  const [topic, setTopic] = useState("");
  const [niche, setNiche] = useState("marketing");
  const [voice, setVoice] = useState(0);
  const [lang, setLang] = useState("en");
  const [tone, setTone] = useState("");
  const [mood, setMood] = useState("");
  const [showAdvanced, setShowAdvanced] = useState(false);
  const [provider, setProvider] = useState("claude_cli");
  const [context, setContext] = useState("");
  const [jobId, setJobId] = useState<string | null>(null);
  const [job, setJob] = useState<JobStatus | null>(null);
  const [polling, setPolling] = useState(false);

  useEffect(() => {
    if (!jobId || !polling) return;
    const interval = setInterval(async () => {
      try {
        const res = await fetch(`${API}/api/status/${jobId}`);
        const data: JobStatus = await res.json();
        setJob(data);
        if (data.status === "done" || data.status === "error") setPolling(false);
      } catch { /* retry */ }
    }, 1500);
    return () => clearInterval(interval);
  }, [jobId, polling]);

  const handleGenerate = async () => {
    if (!topic.trim()) return;
    try {
      const res = await fetch(`${API}/api/generate`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          topic: topic.trim(),
          niche,
          language: lang,
          voice_index: voice,
          provider,
          context: [
            context,
            tone ? `Tone: ${tone}` : "",
            mood ? `Mood: ${mood}` : "",
          ].filter(Boolean).join(". "),
        }),
      });
      const data = await res.json();
      setJobId(data.job_id);
      setJob({ status: "running", stage: "Starting...", progress: 5, draft: null, video_path: null, error: null });
      setPolling(true);
    } catch {
      alert("Cannot connect to backend. Run: python server.py");
    }
  };

  const handleReset = () => { setJobId(null); setJob(null); setTopic(""); setPolling(false); };

  const getActiveStage = () => {
    if (!job?.stage) return -1;
    const s = job.stage.toLowerCase();
    for (let i = STAGES.length - 1; i >= 0; i--) {
      if (STAGES[i].match.some(m => s.includes(m))) return i;
    }
    return 0;
  };

  const activeStage = getActiveStage();
  const isDone = job?.status === "done";
  const isError = job?.status === "error";

  // ── Shared styles ──
  const input = "w-full px-4 py-2.5 rounded-xl text-sm outline-none transition-all";
  const inputStyle = { background: '#0f1011', border: '1px solid rgba(255,255,255,0.08)', color: '#f7f8f8' };

  return (
    <div className="min-h-screen flex flex-col" style={{ background: '#08090a' }}>

      {/* ─── Header ─── */}
      <header className="px-6 py-4 flex items-center gap-3" style={{ borderBottom: '1px solid rgba(255,255,255,0.06)', background: '#0f1011' }}>
        <div className="w-8 h-8 rounded-lg flex items-center justify-center text-sm font-bold" style={{ background: '#5e6ad2', color: '#fff' }}>V</div>
        <span className="text-lg font-semibold tracking-tight" style={{ color: '#f7f8f8' }}>Verticals</span>
        <span className="text-xs px-2 py-0.5 rounded-full ml-1" style={{ background: '#191a1b', color: '#8a8f98' }}>AI Video Generator</span>
      </header>

      <main className="flex-1 flex items-start justify-center px-4 py-12">
        <div className="w-full max-w-xl">

          {/* ═══════════════════ FORM ═══════════════════ */}
          {!jobId && (
            <div className="animate-slide-up">
              <h1 className="text-3xl font-semibold mb-1" style={{ color: '#f7f8f8', letterSpacing: '-0.5px' }}>Create a Video</h1>
              <p className="mb-8 text-sm" style={{ color: '#8a8f98' }}>
                Enter a topic. We handle the rest — script, footage, voiceover, captions.
              </p>

              {/* Topic */}
              <label className="block text-xs font-medium mb-1.5 uppercase tracking-wider" style={{ color: '#8a8f98' }}>Topic *</label>
              <textarea value={topic} onChange={e => setTopic(e.target.value)} rows={3}
                placeholder="e.g. Strait of Hormuz crisis impact on Indian oil imports and rupee"
                className={`${input} resize-none`} style={inputStyle}
                onFocus={e => e.target.style.borderColor = '#5e6ad2'}
                onBlur={e => e.target.style.borderColor = 'rgba(255,255,255,0.08)'} />

              {/* Niche (grouped) */}
              <div className="mt-4">
                <label className="block text-xs font-medium mb-1.5 uppercase tracking-wider" style={{ color: '#8a8f98' }}>Niche / Audience</label>
                <select value={niche} onChange={e => setNiche(e.target.value)} className={input} style={inputStyle}>
                  {NICHE_GROUPS.map(group => (
                    <optgroup key={group.label} label={group.label}>
                      {group.niches.map(n => <option key={n.id} value={n.id}>{n.name}</option>)}
                    </optgroup>
                  ))}
                </select>
              </div>

              {/* Tone + Mood */}
              <div className="grid grid-cols-2 gap-3 mt-4">
                <div>
                  <label className="block text-xs font-medium mb-1.5 uppercase tracking-wider" style={{ color: '#8a8f98' }}>Tone</label>
                  <select value={tone} onChange={e => setTone(e.target.value)} className={input} style={inputStyle}>
                    {TONES.map(t => <option key={t.value} value={t.value}>{t.label}</option>)}
                  </select>
                </div>
                <div>
                  <label className="block text-xs font-medium mb-1.5 uppercase tracking-wider" style={{ color: '#8a8f98' }}>Mood</label>
                  <select value={mood} onChange={e => setMood(e.target.value)} className={input} style={inputStyle}>
                    {MOODS.map(m => <option key={m.value} value={m.value}>{m.label}</option>)}
                  </select>
                </div>
              </div>

              {/* Language + Voice row */}
              <div className="grid grid-cols-2 gap-3 mt-4">
                <div>
                  <label className="block text-xs font-medium mb-1.5 uppercase tracking-wider" style={{ color: '#8a8f98' }}>Language</label>
                  <select value={lang} onChange={e => setLang(e.target.value)} className={input} style={inputStyle}>
                    {LANGUAGES.map(l => <option key={l.value} value={l.value}>{l.label}</option>)}
                  </select>
                </div>
                <div>
                  <label className="block text-xs font-medium mb-1.5 uppercase tracking-wider" style={{ color: '#8a8f98' }}>Voice</label>
                  <div className="flex gap-2">
                    {[{ idx: 0, label: "Male" }, { idx: 1, label: "Female" }].map(v => (
                      <button key={v.idx} onClick={() => setVoice(v.idx)}
                        className="flex-1 py-2.5 rounded-xl text-sm font-medium transition-all cursor-pointer"
                        style={{
                          background: voice === v.idx ? '#5e6ad2' : '#0f1011',
                          color: voice === v.idx ? '#fff' : '#8a8f98',
                          border: `1px solid ${voice === v.idx ? '#5e6ad2' : 'rgba(255,255,255,0.08)'}`,
                        }}>
                        {v.label}
                      </button>
                    ))}
                  </div>
                </div>
              </div>

              {/* Advanced */}
              <button onClick={() => setShowAdvanced(!showAdvanced)}
                className="mt-4 text-xs flex items-center gap-1.5 transition-colors cursor-pointer" style={{ color: '#62666d' }}>
                <span style={{ display: 'inline-block', transform: showAdvanced ? 'rotate(90deg)' : 'none', transition: 'transform 0.2s' }}>&#9654;</span>
                Advanced Settings
              </button>

              {showAdvanced && (
                <div className="mt-2 p-4 rounded-xl animate-slide-up space-y-3" style={{ background: '#0f1011', border: '1px solid rgba(255,255,255,0.08)' }}>
                  <div className="grid grid-cols-2 gap-3">
                    <div>
                      <label className="block text-xs mb-1" style={{ color: '#62666d' }}>LLM Provider</label>
                      <select value={provider} onChange={e => setProvider(e.target.value)}
                        className="w-full px-3 py-2 rounded-lg text-xs outline-none" style={{ background: '#191a1b', border: '1px solid rgba(255,255,255,0.06)', color: '#d0d6e0' }}>
                        <option value="claude_cli">Claude (Max)</option>
                        <option value="claude">Claude (API)</option>
                        <option value="gemini">Gemini</option>
                        <option value="openai">OpenAI</option>
                        <option value="ollama">Ollama (Local)</option>
                      </select>
                    </div>
                    <div>
                      <label className="block text-xs mb-1" style={{ color: '#62666d' }}>Platform</label>
                      <select className="w-full px-3 py-2 rounded-lg text-xs outline-none" style={{ background: '#191a1b', border: '1px solid rgba(255,255,255,0.06)', color: '#d0d6e0' }}>
                        <option>YouTube Shorts</option>
                        <option>Instagram Reels</option>
                        <option>TikTok</option>
                      </select>
                    </div>
                  </div>
                  <div>
                    <label className="block text-xs mb-1" style={{ color: '#62666d' }}>Channel Context</label>
                    <input value={context} onChange={e => setContext(e.target.value)} placeholder="e.g. Indian finance channel for professionals"
                      className="w-full px-3 py-2 rounded-lg text-xs outline-none" style={{ background: '#191a1b', border: '1px solid rgba(255,255,255,0.06)', color: '#d0d6e0' }} />
                  </div>
                </div>
              )}

              {/* CTA */}
              <button onClick={handleGenerate} disabled={!topic.trim()}
                className="mt-8 w-full py-3.5 rounded-xl text-sm font-semibold transition-all cursor-pointer"
                style={{
                  background: topic.trim() ? '#5e6ad2' : '#191a1b',
                  color: topic.trim() ? '#fff' : '#62666d',
                  cursor: topic.trim() ? 'pointer' : 'not-allowed',
                }}
                onMouseEnter={e => { if (topic.trim()) (e.target as HTMLElement).style.background = '#7170ff'; }}
                onMouseLeave={e => { if (topic.trim()) (e.target as HTMLElement).style.background = '#5e6ad2'; }}>
                Generate Video
              </button>
            </div>
          )}

          {/* ═══════════════════ PROGRESS ═══════════════════ */}
          {jobId && !isDone && !isError && (
            <div className="animate-slide-up">
              <h2 className="text-2xl font-semibold mb-1" style={{ color: '#f7f8f8', letterSpacing: '-0.3px' }}>Generating your video...</h2>
              <p className="text-sm mb-6" style={{ color: '#8a8f98' }}>This takes 2-4 minutes. Sit tight.</p>

              {/* Bar */}
              <div className="w-full h-1 rounded-full mb-8" style={{ background: '#191a1b' }}>
                <div className="h-full rounded-full transition-all duration-1000 ease-out" style={{ width: `${job?.progress || 0}%`, background: '#5e6ad2' }} />
              </div>

              {/* Stages */}
              <div className="space-y-1">
                {STAGES.map((stage, i) => {
                  const done = activeStage > i || (job?.progress || 0) >= 98;
                  const active = activeStage === i;
                  return (
                    <div key={stage.key} className="flex items-center gap-3 py-2.5 px-4 rounded-xl transition-all"
                      style={{
                        background: active ? 'rgba(94,106,210,0.06)' : 'transparent',
                        border: active ? '1px solid rgba(94,106,210,0.15)' : '1px solid transparent',
                      }}>
                      <div className="w-5 h-5 rounded-full flex items-center justify-center text-[10px] font-medium shrink-0"
                        style={{
                          background: done ? '#27a644' : active ? '#5e6ad2' : '#191a1b',
                          color: done || active ? '#fff' : '#62666d',
                        }}>
                        {done ? "\u2713" : i + 1}
                      </div>
                      <span className={`text-sm ${active ? 'animate-progress font-medium' : ''}`}
                        style={{ color: done ? '#8a8f98' : active ? '#f7f8f8' : '#62666d' }}>
                        {stage.label}{active ? "..." : ""}
                      </span>
                    </div>
                  );
                })}
              </div>

              {/* Script preview */}
              {job?.draft && (
                <div className="mt-6 p-4 rounded-xl animate-slide-up" style={{ background: '#0f1011', border: '1px solid rgba(255,255,255,0.06)' }}>
                  <p className="text-xs font-medium mb-2 uppercase tracking-wider" style={{ color: '#5e6ad2' }}>Script Preview</p>
                  <p className="text-xs leading-relaxed" style={{ color: '#8a8f98' }}>
                    {(job.draft as Record<string, string>).script?.substring(0, 250)}...
                  </p>
                </div>
              )}
            </div>
          )}

          {/* ═══════════════════ ERROR ═══════════════════ */}
          {jobId && isError && (
            <div className="animate-slide-up">
              <div className="p-5 rounded-xl" style={{ background: 'rgba(239,68,68,0.06)', border: '1px solid rgba(239,68,68,0.15)' }}>
                <h2 className="text-base font-semibold mb-2" style={{ color: '#ef4444' }}>Generation Failed</h2>
                <p className="text-sm" style={{ color: '#d0d6e0' }}>{job?.error}</p>
              </div>
              <button onClick={handleReset} className="mt-4 px-5 py-2.5 rounded-xl text-sm font-medium cursor-pointer"
                style={{ background: '#191a1b', color: '#d0d6e0', border: '1px solid rgba(255,255,255,0.08)' }}>
                Try Again
              </button>
            </div>
          )}

          {/* ═══════════════════ RESULT ═══════════════════ */}
          {jobId && isDone && (
            <div className="animate-slide-up">
              <div className="flex items-center gap-2 mb-1">
                <div className="w-5 h-5 rounded-full flex items-center justify-center" style={{ background: '#27a644' }}>
                  <span className="text-white text-[10px]">&#10003;</span>
                </div>
                <h2 className="text-2xl font-semibold" style={{ color: '#f7f8f8', letterSpacing: '-0.3px' }}>Video Ready</h2>
              </div>
              <p className="text-sm mb-6" style={{ color: '#8a8f98' }}>
                {(job?.draft as Record<string, string>)?.youtube_title || ""}
              </p>

              {/* Player */}
              <div className="rounded-2xl overflow-hidden mb-5" style={{ background: '#000', border: '1px solid rgba(255,255,255,0.06)' }}>
                <video src={`${API}/api/videos/${jobId}`} controls className="w-full" style={{ maxHeight: '65vh' }} />
              </div>

              {/* Buttons */}
              <div className="flex gap-3 mb-6">
                <a href={`${API}/api/videos/${jobId}`} download
                  className="flex-1 py-3 rounded-xl text-sm font-semibold text-center transition-all no-underline"
                  style={{ background: '#5e6ad2', color: '#fff' }}
                  onMouseEnter={e => (e.target as HTMLElement).style.background = '#7170ff'}
                  onMouseLeave={e => (e.target as HTMLElement).style.background = '#5e6ad2'}>
                  Download
                </a>
                <button onClick={handleReset}
                  className="flex-1 py-3 rounded-xl text-sm font-medium transition-all cursor-pointer"
                  style={{ background: 'transparent', color: '#d0d6e0', border: '1px solid rgba(255,255,255,0.08)' }}>
                  Make Another
                </button>
              </div>

              {/* Script */}
              {job?.draft && (
                <div className="p-5 rounded-xl" style={{ background: '#0f1011', border: '1px solid rgba(255,255,255,0.06)' }}>
                  <p className="text-xs font-medium mb-2 uppercase tracking-wider" style={{ color: '#5e6ad2' }}>Script</p>
                  <p className="text-sm leading-relaxed mb-4" style={{ color: '#d0d6e0' }}>
                    {(job.draft as Record<string, string>).script}
                  </p>
                  <div className="pt-3 flex flex-wrap gap-1.5" style={{ borderTop: '1px solid rgba(255,255,255,0.06)' }}>
                    {(job.draft as Record<string, string>).youtube_tags?.split(",").map((tag: string) => (
                      <span key={tag} className="text-[10px] px-2 py-0.5 rounded-md" style={{ background: '#191a1b', color: '#62666d' }}>
                        {tag.trim()}
                      </span>
                    ))}
                  </div>
                </div>
              )}
            </div>
          )}

        </div>
      </main>

      <footer className="py-3 text-center text-[10px] uppercase tracking-wider" style={{ color: '#28282c' }}>
        Verticals v3 Enhanced Fork
      </footer>
    </div>
  );
}
