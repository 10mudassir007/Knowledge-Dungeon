import { Trophy, Skull, RotateCcw } from "lucide-react";

interface GameOverScreenProps {
  won: boolean;
  points: number;
  level: number;
  name: string;
  onRestart: () => void;
}

const GameOverScreen = ({ won, points, level, name, onRestart }: GameOverScreenProps) => {
  return (
    <div className="min-h-screen dungeon-gradient flex items-center justify-center p-4">
      <div className="text-center animate-fade-in max-w-md">
        <div className="mb-6">
          {won ? (
            <Trophy className="w-20 h-20 text-accent mx-auto float-animation" />
          ) : (
            <Skull className="w-20 h-20 text-destructive mx-auto shake" />
          )}
        </div>

        <h1 className={`font-pixel text-2xl mb-3 ${won ? "neon-text-gold" : "neon-text-red"}`}>
          {won ? "VICTORY!" : "GAME OVER"}
        </h1>

        <p className="text-muted-foreground font-body text-lg mb-6">
          {won
            ? `Incredible, ${name}! You conquered the Knowledge Dungeon!`
            : `The dungeon claims another soul... Better luck next time, ${name}.`}
        </p>

        <div className="game-card inline-block mb-8">
          <div className="flex gap-8">
            <div>
              <p className="font-pixel text-xs text-primary mb-1">POINTS</p>
              <p className="font-pixel text-xl neon-text-gold">{points}</p>
            </div>
            <div>
              <p className="font-pixel text-xs text-primary mb-1">LEVEL</p>
              <p className="font-pixel text-xl neon-text">{level}</p>
            </div>
          </div>
        </div>

        <div>
          <button
            onClick={onRestart}
            className="bg-primary text-primary-foreground font-pixel text-sm py-4 px-8 rounded-md hover:brightness-110 transition-all neon-box flex items-center gap-2 mx-auto"
          >
            <RotateCcw className="w-4 h-4" />
            PLAY AGAIN
          </button>
        </div>
      </div>
    </div>
  );
};

export default GameOverScreen;
