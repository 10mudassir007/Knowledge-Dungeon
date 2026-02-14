import { Heart, Star, Layers, User } from "lucide-react";

interface HUDProps {
  name: string;
  lives: number;
  points: number;
  level: number;
}

const HUD = ({ name, lives, points, level }: HUDProps) => {
  return (
    <div className="w-full flex flex-wrap items-center justify-between gap-3 px-4 py-3 bg-card border-b border-border">
      {/* Player name */}
      <div className="flex items-center gap-2">
        <User className="w-4 h-4 text-secondary" />
        <span className="font-pixel text-xs neon-text-purple">{name}</span>
      </div>

      <div className="flex items-center gap-5">
        {/* Lives */}
        <div className="flex items-center gap-1">
          {Array.from({ length: 3 }).map((_, i) => (
            <Heart
              key={i}
              className={`w-5 h-5 transition-all ${
                i < lives
                  ? "text-destructive fill-destructive heart-pulse"
                  : "text-muted-foreground opacity-30"
              }`}
              style={{ animationDelay: `${i * 0.2}s` }}
            />
          ))}
        </div>

        {/* Points */}
        <div className="flex items-center gap-1.5">
          <Star className="w-4 h-4 text-accent fill-accent" />
          <span className="font-pixel text-xs neon-text-gold">{points}</span>
        </div>

        {/* Level */}
        <div className="flex items-center gap-1.5">
          <Layers className="w-4 h-4 text-primary" />
          <span className="font-pixel text-xs neon-text">LV{level}</span>
        </div>
      </div>
    </div>
  );
};

export default HUD;
