/**
 * First-person movement with grid collision.
 *
 * Collision uses src/world/map.ts (never GLB geometry): a body of radius R is
 * moved on one axis at a time so the player slides along walls.
 */

import { useEffect, useRef } from "react";
import { useFrame, useThree } from "@react-three/fiber";
import * as THREE from "three";
import { canStand } from "./map";
import { playSfx } from "../audio/sound";

export const EYE_HEIGHT = 1.6;
export const PLAYER_RADIUS = 0.35;
const MOVE_SPEED = 3.4;
const SPRINT_SPEED = 5.9;
const TURN_SPEED = 2.2;
/** Keeps the camera from ending up inside an orc's body. */
const BODY_RADIUS = 0.75;
/** How far the view can tilt up/down from the horizon, in radians (~77 degrees). */
const MAX_PITCH = 1.35;

export interface Blocker {
  x: number;
  z: number;
}

export interface PlayerProps {
  start: [number, number, number];
  yaw: number;
  /** Movement is locked while a dialogue is open. */
  locked: boolean;
  /** Dynamic obstacles (orcs) that also stop the player. */
  blockers?: Blocker[];
  /** Releasing pointer lock should not steal the cursor back. */
  onLockChange?: (locked: boolean) => void;
  onPointerLockUnavailable?: () => void;
  /** Death: the camera collapses to the floor and rolls onto its side. */
  dead?: boolean;
  /** Changes on every new run; returning the player to spawn is keyed off it. */
  resetKey?: number | string;
}

export function Player({
  start,
  yaw,
  locked,
  blockers = [],
  dead = false,
  resetKey,
  onLockChange,
  onPointerLockUnavailable,
}: PlayerProps) {
  const { camera, gl } = useThree();
  const keys = useRef<Record<string, boolean>>({});
  const pos = useRef(new THREE.Vector3(start[0], EYE_HEIGHT, start[2]));
  const angle = useRef(yaw);
  const pitch = useRef(0);
  // 0 = standing, 1 = collapsed on the floor.
  const collapse = useRef(0);
  const lastDead = useRef(dead);
  const stepDistance = useRef(0);
  const lastFootstep = useRef(0);

  // Cells holding water, so walking through a pool splashes instead of thuds.

  useEffect(() => {
    pos.current.set(start[0], EYE_HEIGHT, start[2]);
    angle.current = yaw;
    pitch.current = 0;
    camera.position.set(start[0], EYE_HEIGHT, start[2]);
    collapse.current = 0;
    lastDead.current = dead;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [start, resetKey]);

  useEffect(() => {
    const canvas = gl.domElement;

    const onKeyDown = (e: KeyboardEvent) => {
      keys.current[e.code] = true;
    };
    const onKeyUp = (e: KeyboardEvent) => {
      keys.current[e.code] = false;
    };
    const onMouseMove = (e: MouseEvent) => {
      if (document.pointerLockElement !== canvas) return;
      angle.current -= e.movementX * 0.0022;
      pitch.current = Math.max(
        -MAX_PITCH,
        Math.min(MAX_PITCH, pitch.current - e.movementY * 0.0022),
      );
    };
    const handleLockChange = () => {
      const isLocked = document.pointerLockElement === canvas;
      onLockChange?.(isLocked);
      if (!isLocked) keys.current = {};
    };

    if (typeof canvas.requestPointerLock !== "function") {
      // Arrow keys remain as the fallback.
      onPointerLockUnavailable?.();
    }

    window.addEventListener("keydown", onKeyDown);
    window.addEventListener("keyup", onKeyUp);
    document.addEventListener("mousemove", onMouseMove);
    document.addEventListener("pointerlockchange", handleLockChange);
    return () => {
      window.removeEventListener("keydown", onKeyDown);
      window.removeEventListener("keyup", onKeyUp);
      document.removeEventListener("mousemove", onMouseMove);
      document.removeEventListener("pointerlockchange", handleLockChange);
    };
  }, [gl, onLockChange, onPointerLockUnavailable]);

  useFrame(() => {
    const k = keys.current;
    const forward = (k.KeyW ? 1 : 0) - (k.KeyS ? 1 : 0);
    const strafe = (k.KeyD ? 1 : 0) - (k.KeyA ? 1 : 0);
    // Arrow-key fallback for when pointer lock is unavailable.
    const turn = (k.ArrowLeft ? 1 : 0) - (k.ArrowRight ? 1 : 0);
    if (turn !== 0) angle.current += turn * TURN_SPEED * (1 / 60);

    const sin = Math.sin(angle.current);
    const cos = Math.cos(angle.current);
    let dx = forward * -sin + strafe * cos;
    let dz = forward * -cos + strafe * -sin;
    const len = Math.hypot(dx, dz);
    // Movement is locked while a dialogue or the pause menu is open.
    if (len > 0 && !locked) {
      // Holding Left Shift sprints; it only ever speeds you up, never slows.
      const sprinting = Boolean(k.ShiftLeft || k.ShiftRight);
      const speed = sprinting ? SPRINT_SPEED : MOVE_SPEED;
      dx = (dx / len) * speed * (1 / 60);
      dz = (dz / len) * speed * (1 / 60);

      const r = PLAYER_RADIUS;
      const cur = pos.current;

      const blockedByBody = (x: number, z: number) =>
        blockers.some((b) => Math.hypot(x - b.x, z - b.z) < BODY_RADIUS + PLAYER_RADIUS);

      // Slide: try the X move alone, then the Z move alone.
      const px = cur.x;
      const pz = cur.z;
      if (canStand(cur.x + dx, cur.z, r) && !blockedByBody(cur.x + dx, cur.z)) cur.x += dx;
      if (canStand(cur.x, cur.z + dz, r) && !blockedByBody(cur.x, cur.z + dz)) cur.z += dz;

      // Footsteps, spaced by distance travelled; pools splash instead.
      stepDistance.current += Math.hypot(cur.x - px, cur.z - pz);
      if (stepDistance.current >= 1.7) {
        stepDistance.current = 0;
        const now = performance.now();
        if (now - lastFootstep.current > 120) {
          lastFootstep.current = now;
          playSfx(sprinting ? "sprint" : "footstep");
        }
      }
    }

    camera.position.set(pos.current.x, EYE_HEIGHT, pos.current.z);
    camera.rotation.set(pitch.current, angle.current, 0, "YXZ");

    // Death: release the pointer lock, then slump the camera down to the floor.
    if (dead !== lastDead.current) {
      lastDead.current = dead;
      if (dead) {
        if (document.pointerLockElement === gl.domElement) document.exitPointerLock();
      } else {
        collapse.current = 0;
      }
    }

    if (dead) {
      // Ease into the fall rather than snapping; ~1.1s from upright to floor.
      collapse.current = Math.min(1, collapse.current + (1 / 60) * 1.1);
      const c = collapse.current;
      const eased = c * c * (3 - 2 * c);
      camera.position.set(
        pos.current.x,
        THREE.MathUtils.lerp(EYE_HEIGHT, 0.22, eased),
        pos.current.z,
      );
      // Pitch down onto the floor, then roll onto one side.
      camera.rotation.set(
        THREE.MathUtils.lerp(0, -1.15, eased),
        angle.current,
        THREE.MathUtils.lerp(0, 0.55, eased),
        "YXZ",
      );
    }
  });

  return null;
}