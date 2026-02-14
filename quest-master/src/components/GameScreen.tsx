import { useState } from "react";
import { Send, Lightbulb, Loader2 } from "lucide-react";

interface GameScreenProps {
  question: string;
  environment: string;
  onSubmitAnswer: (answer: string) => void;
  onRequestHint: () => void;
  hint: string | null;
  loadingAnswer: boolean;
  loadingHint: boolean;
  verdict: string | null;
  correctAnswer: string;
}

const GameScreen = ({
  question,
  environment,
  onSubmitAnswer,
  onRequestHint,
  hint,
  loadingAnswer,
  loadingHint,
  verdict,
  correctAnswer,
}: GameScreenProps) => {
  const [answer, setAnswer] = useState("");

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (answer.trim() && !loadingAnswer) {
      onSubmitAnswer(answer.trim());
      setAnswer("");
    }
  };

  const isIncorrect = verdict?.toLowerCase().includes("incorrect");

  return (
    <div className="flex-1 flex flex-col p-4 md:p-6 max-w-2xl mx-auto w-full animate-fade-in">
      {/* Title */}
      <div className="mb-4 text-center">
        <h1 className="font-pixel text-sm md:text-base neon-text tracking-wider">
          Knowledge Dungeon
        </h1>
      </div>

      {/* Environment */}
      <div className="game-card mb-4 text-sm text-muted-foreground italic border-secondary/30">
        <p>🏰 {environment}</p>
      </div>

      {/* Question */}
      <div className="game-card mb-4 flex-shrink-0">
        <h2 className="font-pixel text-xs text-primary mb-3 tracking-wider">
          QUESTION
        </h2>
        <p className="text-foreground font-body text-xl leading-relaxed">
          {question}
        </p>
      </div>

      {/* Verdict */}
      {verdict && (
        <div
          className={`game-card mb-4 animate-scale-in ${
            verdict.toLowerCase().includes("correct")
              ? "border-primary/50"
              : "border-destructive/50"
          }`}
        >
          <p className="font-body text-lg">{verdict}</p>

          {isIncorrect && correctAnswer && (
            <p className="mt-2 font-body text-base text-muted-foreground">
              Correct answer:{" "}
              <span className="neon-text-gold">{correctAnswer}</span>
            </p>
          )}
        </div>
      )}

      {/* Hint */}
      {hint && (
        <div className="game-card mb-4 border-accent/30 animate-scale-in">
          <h3 className="font-pixel text-xs text-accent mb-2">💡 HINT</h3>
          <p className="text-muted-foreground font-body text-base">{hint}</p>
        </div>
      )}

      {/* Spacer */}
      <div className="flex-1" />

      {/* Actions */}
      <div className="space-y-3">
        <button
          onClick={onRequestHint}
          disabled={loadingHint || !!hint}
          className="w-full bg-muted border border-accent/30 text-accent font-pixel text-xs py-3 rounded-md hover:bg-accent/10 transition-all disabled:opacity-30 disabled:cursor-not-allowed flex items-center justify-center gap-2"
        >
          {loadingHint ? (
            <Loader2 className="w-4 h-4 animate-spin" />
          ) : (
            <Lightbulb className="w-4 h-4" />
          )}
          {hint ? "HINT USED" : "GET HINT"}
        </button>

        <form onSubmit={handleSubmit} className="flex gap-2">
          <input
            type="text"
            value={answer}
            onChange={(e) => setAnswer(e.target.value)}
            placeholder="Type your answer..."
            className="flex-1 bg-muted border border-border rounded-md px-4 py-3 text-foreground font-body text-lg placeholder:text-muted-foreground focus:outline-none focus:neon-border transition-all"
            disabled={loadingAnswer}
          />
          <button
            type="submit"
            disabled={loadingAnswer || !answer.trim()}
            className="bg-primary text-primary-foreground px-5 py-3 rounded-md hover:brightness-110 transition-all disabled:opacity-40 disabled:cursor-not-allowed neon-box"
          >
            {loadingAnswer ? (
              <Loader2 className="w-5 h-5 animate-spin" />
            ) : (
              <Send className="w-5 h-5" />
            )}
          </button>
        </form>
      </div>
    </div>
  );
};

export default GameScreen;
