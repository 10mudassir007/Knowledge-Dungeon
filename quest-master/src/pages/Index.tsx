import { useState, useCallback, useRef } from "react";
import { api, type QuestionResponse, type StartGameResponse } from "@/lib/api";
import EntryScreen from "@/components/EntryScreen";
import GameScreen from "@/components/GameScreen";
import GameOverScreen from "@/components/GameOverScreen";
import HUD from "@/components/HUD";
import { toast } from "sonner";

type Screen = "entry" | "game" | "gameover";

const Index = () => {
  const [screen, setScreen] = useState<Screen>("entry");
  const [playerName, setPlayerName] = useState("");
  const [sessionId, setSessionId] = useState("");
  const [lives, setLives] = useState(3);
  const [points, setPoints] = useState(0);
  const [level, setLevel] = useState(1);
  const [environment, setEnvironment] = useState("");
  const [question, setQuestion] = useState("");
  const [correctAnswer, setCorrectAnswer] = useState("");
  const [hint, setHint] = useState<string | null>(null);
  const [verdict, setVerdict] = useState<string | null>(null);
  const [won, setWon] = useState(false);

  const [showLevelUp, setShowLevelUp] = useState(false);
  const prevLevelRef = useRef(1);

  const [loadingStart, setLoadingStart] = useState(false);
  const [loadingAnswer, setLoadingAnswer] = useState(false);
  const [loadingHint, setLoadingHint] = useState(false);

  const fetchQuestion = useCallback(async (sid: string) => {
    try {
      const q = await api.getQuestion(sid);
      setQuestion(q.question);
      setCorrectAnswer(q.correct_answer);
      setLives(q.lives);
      setPoints(q.points);
      setLevel(q.level);
      setHint(null);
      setVerdict(null);
    } catch {
      toast.error("Failed to fetch question");
    }
  }, []);

  const handleStart = async (name: string, age: number, interest: string) => {
    setLoadingStart(true);
    try {
      const res: StartGameResponse = await api.startGame({ age, interest });
      setPlayerName(name);
      setSessionId(res.session_id);
      setLives(res.lives);
      setPoints(res.points);
      setLevel(res.level);
      prevLevelRef.current = res.level;
      setEnvironment(res.environment);
      await fetchQuestion(res.session_id);
      setScreen("game");
    } catch {
      toast.error("Failed to start game. Is the server running?");
    } finally {
      setLoadingStart(false);
    }
  };

  const handleAnswer = async (userAnswer: string) => {
    setLoadingAnswer(true);
    try {
      const res = await api.checkAnswer(sessionId, {
        question,
        correct_answer: correctAnswer,
        user_answer: userAnswer,
      });

      setVerdict(res.verdict);
      setLives(res.lives);
      setPoints(res.points);

      // Detect level-up and play animation
      const prevLevel = prevLevelRef.current;
      if (res.level > prevLevel) {
        setShowLevelUp(true);
        window.setTimeout(() => setShowLevelUp(false), 1400);
      }
      prevLevelRef.current = res.level;
      setLevel(res.level);

      if (res.won || res.game_over) {
        setWon(res.won);
        setTimeout(() => setScreen("gameover"), 2000);
      } else {
        // Fetch new environment if leveled up, then next question
        try {
          const env = await api.getEnvironment(sessionId);
          setEnvironment(env.environment);
        } catch {}
        setTimeout(() => fetchQuestion(sessionId), 2000);
      }
    } catch {
      toast.error("Failed to check answer");
    } finally {
      setLoadingAnswer(false);
    }
  };

  const handleHint = async () => {
    setLoadingHint(true);
    try {
      const res = await api.getHint(sessionId, { question, correct_answer: correctAnswer });
      setHint(res.hint);
    } catch {
      toast.error("Failed to get hint");
    } finally {
      setLoadingHint(false);
    }
  };

  const handleRestart = () => {
    setScreen("entry");
    setSessionId("");
    setPlayerName("");
    setHint(null);
    setVerdict(null);
    setShowLevelUp(false);
    prevLevelRef.current = 1;
  };

  if (screen === "entry") {
    return <EntryScreen onStart={handleStart} loading={loadingStart} />;
  }

  if (screen === "gameover") {
    return (
      <GameOverScreen
        won={won}
        points={points}
        level={level}
        name={playerName}
        onRestart={handleRestart}
      />
    );
  }

  return (
    <div className="min-h-screen dungeon-gradient flex flex-col">
      <HUD name={playerName} lives={lives} points={points} level={level} />

      {showLevelUp && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60">
          <div className="game-card border-primary/50 neon-box animate-level-up text-center">
            <div className="font-pixel text-sm neon-text">LEVEL UP</div>
            <div className="mt-3 font-pixel text-2xl neon-text-gold">LV {level}</div>
          </div>
        </div>
      )}

      <GameScreen
        question={question}
        environment={environment}
        onSubmitAnswer={handleAnswer}
        onRequestHint={handleHint}
        hint={hint}
        loadingAnswer={loadingAnswer}
        loadingHint={loadingHint}
        verdict={verdict}
        correctAnswer={correctAnswer}
      />
    </div>
  );
};

export default Index;
