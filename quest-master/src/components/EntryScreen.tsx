import { useState } from "react";
import { Sword, Shield, Sparkles } from "lucide-react";

interface EntryScreenProps {
  onStart: (name: string, age: number, interest: string) => void;
  loading: boolean;
}

const EntryScreen = ({ onStart, loading }: EntryScreenProps) => {
  const [name, setName] = useState("");
  const [age, setAge] = useState("");
  const [interest, setInterest] = useState("");

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (name.trim() && age && interest.trim()) {
      onStart(name.trim(), parseInt(age), interest.trim());
    }
  };

  return (
    <div className="min-h-screen dungeon-gradient flex items-center justify-center p-4">
      <div className="w-full max-w-md animate-fade-in">
        {/* Title */}
        <div className="text-center mb-8">
          <div className="flex items-center justify-center gap-3 mb-4">
            <Sword className="w-8 h-8 text-primary glow-pulse" />
            <Shield className="w-10 h-10 text-accent float-animation" />
            <Sword className="w-8 h-8 text-primary glow-pulse" style={{ transform: "scaleX(-1)" }} />
          </div>
          <h1 className="font-pixel text-2xl md:text-3xl neon-text mb-3 leading-relaxed">
            KNOWLEDGE
            <br />
            DUNGEON
          </h1>
          <p className="text-muted-foreground font-body text-lg">
            Enter the dungeon. Answer to survive.
          </p>
        </div>

        {/* Form */}
        <form onSubmit={handleSubmit} className="game-card space-y-5">
          <div>
            <label className="block font-pixel text-xs text-primary mb-2">HERO NAME</label>
            <input
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="Enter your name..."
              className="w-full bg-muted border border-border rounded-md px-4 py-3 text-foreground font-body text-lg placeholder:text-muted-foreground focus:outline-none focus:neon-border transition-all"
              required
            />
          </div>

          <div>
            <label className="block font-pixel text-xs text-primary mb-2">AGE</label>
            <input
              type="number"
              value={age}
              onChange={(e) => setAge(e.target.value)}
              placeholder="Your age..."
              min={1}
              max={120}
              className="w-full bg-muted border border-border rounded-md px-4 py-3 text-foreground font-body text-lg placeholder:text-muted-foreground focus:outline-none focus:neon-border transition-all"
              required
            />
          </div>

          <div>
            <label className="block font-pixel text-xs text-primary mb-2">INTEREST</label>
            <input
              type="text"
              value={interest}
              onChange={(e) => setInterest(e.target.value)}
              placeholder="e.g. Science, History, Sports..."
              maxLength={80}
              className="w-full bg-muted border border-border rounded-md px-4 py-3 text-foreground font-body text-lg placeholder:text-muted-foreground focus:outline-none focus:neon-border transition-all"
              required
            />
          </div>

          <button
            type="submit"
            disabled={loading || !name.trim() || !age || !interest.trim()}
            className="w-full bg-primary text-primary-foreground font-pixel text-sm py-4 rounded-md hover:brightness-110 transition-all disabled:opacity-40 disabled:cursor-not-allowed neon-box flex items-center justify-center gap-2"
          >
            {loading ? (
              <span className="animate-pulse">ENTERING DUNGEON...</span>
            ) : (
              <>
                <Sparkles className="w-4 h-4" />
                START QUEST
                <Sparkles className="w-4 h-4" />
              </>
            )}
          </button>
        </form>
      </div>
    </div>
  );
};

export default EntryScreen;
