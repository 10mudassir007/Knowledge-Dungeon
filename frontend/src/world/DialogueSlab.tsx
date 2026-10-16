import { useEffect, useMemo, useRef, useState } from "react";
import { useFrame, useThree } from "@react-three/fiber";
import * as THREE from "three";

/**
 * A carved stone slab that hovers beside the active orc.
 *
 * The DOM overlay (EnemyDialogue) is projected onto the same screen point, so
 * the text reads as being *on* the slab rather than floating in a HUD layer.
 */
export function DialogueSlab({
  anchorRef,
  height,
  reducedMotion,
}: {
  /** World-space position of the active orc's head, updated every frame. */
  anchorRef: React.MutableRefObject<[number, number, number] | null>;
  height: number;
  reducedMotion: boolean;
}) {
  const group = useRef<THREE.Group>(null);
  const { camera } = useThree();
  const glow = useRef<THREE.Mesh>(null);
  const [visible, setVisible] = useState(false);

  const stone = useMemo(() => {
    const canvas = document.createElement("canvas");
    canvas.width = 256;
    canvas.height = 256;
    const ctx = canvas.getContext("2d") as CanvasRenderingContext2D;
    const g = ctx.createRadialGradient(128, 128, 20, 128, 128, 150);
    g.addColorStop(0, "#2a2440");
    g.addColorStop(1, "#0d0a16");
    ctx.fillStyle = g;
    ctx.fillRect(0, 0, 256, 256);
    // Carved rune flecks.
    ctx.strokeStyle = "rgba(180,160,255,0.16)";
    for (let i = 0; i < 90; i += 1) {
      const x = Math.random() * 256;
      const y = Math.random() * 256;
      const len = 4 + Math.random() * 22;
      ctx.beginPath();
      ctx.moveTo(x, y);
      ctx.lineTo(x + len * 0.7, y - len);
      ctx.stroke();
    }
    const tex = new THREE.CanvasTexture(canvas);
    tex.colorSpace = THREE.SRGBColorSpace;
    return new THREE.MeshStandardMaterial({
      map: tex,
      emissive: new THREE.Color("#2a1f5c"),
      emissiveIntensity: 0.9,
      roughness: 0.85,
      metalness: 0.1,
      transparent: true,
      opacity: 0.94,
    });
  }, []);

  const frame = useMemo(
    () => new THREE.MeshStandardMaterial({ color: "#6b5a3a", roughness: 0.5, metalness: 0.7 }),
    [],
  );
  const rune = useMemo(
    () => new THREE.MeshStandardMaterial({ color: "#b9a6ff", emissive: "#7a5cff", emissiveIntensity: 2.2 }),
    [],
  );

  useEffect(() => {
    setVisible(Boolean(anchorRef.current));
  }, [anchorRef]);

  useFrame(({ clock }) => {
    const g = group.current;
    const anchor = anchorRef.current;
    if (!g) return;
    g.visible = Boolean(anchor);
    if (!anchor) return;

    g.position.set(anchor[0], anchor[1] + height, anchor[2]);
    // Billboard around Y only so the slab always faces the player.
    g.rotation.y = Math.atan2(camera.position.x - anchor[0], camera.position.z - anchor[2]);
    if (glow.current) {
      const mat = glow.current.material as THREE.MeshBasicMaterial;
      const pulse = reducedMotion ? 1 : 0.55 + 0.45 * Math.sin(clock.elapsedTime * 2.2);
      mat.opacity = 0.18 * pulse;
    }
  });

  // The slab is always in the scene graph; visibility is driven per-frame above.
  return (
    <group ref={group} visible={visible}>
      {/* slab */}
      <mesh material={stone}>
        <boxGeometry args={[1.15, 0.78, 0.04]} />
      </mesh>
      {/* carved frame */}
      {[
        [0, 0.42, 1.22, 0.06],
        [0, -0.42, 1.22, 0.06],
      ].map(([x, y, w, h], i) => (
        <mesh key={`h${i}`} position={[x, y, 0.03]} material={frame}>
          <boxGeometry args={[w, h, 0.05]} />
        </mesh>
      ))}
      {[-0.58, 0.58].map((x, i) => (
        <mesh key={`v${i}`} position={[x, 0, 0.03]} material={frame}>
          <boxGeometry args={[0.06, 0.9, 0.05]} />
        </mesh>
      ))}
      {/* runes */}
      {[-0.3, 0, 0.3].map((x, i) => (
        <mesh key={`r${i}`} position={[x, 0.33, 0.06]} material={rune}>
          <boxGeometry args={[0.05, 0.05, 0.02]} />
        </mesh>
      ))}
      {/* soft glow behind the slab */}
      <mesh ref={glow} position={[0, 0, -0.08]}>
        <planeGeometry args={[1.9, 1.4]} />
        <meshBasicMaterial color="#6a4cff" transparent opacity={0.18} depthWrite={false} />
      </mesh>
    </group>
  );
}