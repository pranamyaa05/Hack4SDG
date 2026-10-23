import { useEffect, useRef, useState } from "react";
import * as THREE from "three";
import { OrbitControls } from "three/examples/jsm/controls/OrbitControls.js";
import { STLLoader } from "three/examples/jsm/loaders/STLLoader.js";
export default function Viewer({ url }: { url: string }) {
  const host = useRef<HTMLDivElement>(null);
  const [error, setError] = useState("");
  useEffect(() => {
    const el = host.current;
    if (!el) return;
    let disposed = false;
    let frame = 0;
    let mesh: THREE.Mesh | undefined;
    let renderer: THREE.WebGLRenderer;
    try {
      renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
    } catch {
      setError(
        "3D preview is unavailable on this device. You can still download the STL.",
      );
      return;
    }
    const scene = new THREE.Scene();
    scene.background = new THREE.Color("#e7eee7");
    const camera = new THREE.PerspectiveCamera(40, 1, 0.1, 3000);
    camera.up.set(0, 0, 1);
    const controls = new OrbitControls(camera, renderer.domElement);
    controls.enableDamping = true;
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    el.appendChild(renderer.domElement);
    scene.add(new THREE.HemisphereLight(0xffffff, 0x405748, 3));
    const light = new THREE.DirectionalLight(0xffffff, 4);
    light.position.set(50, -70, 100);
    scene.add(light);
    const resize = () => {
      const w = el.clientWidth,
        h = el.clientHeight;
      renderer.setSize(w, h);
      camera.aspect = w / h;
      camera.updateProjectionMatrix();
    };
    const observer = new ResizeObserver(resize);
    observer.observe(el);
    resize();
    const controller = new AbortController();
    fetch(url, { signal: controller.signal })
      .then((r) => {
        if (!r.ok) throw Error();
        return r.arrayBuffer();
      })
      .then((buffer) => {
        if (disposed) return;
        const geometry = new STLLoader().parse(buffer);
        geometry.computeVertexNormals();
        geometry.center();
        geometry.computeBoundingSphere();
        const radius = geometry.boundingSphere?.radius || 50;
        mesh = new THREE.Mesh(
          geometry,
          new THREE.MeshStandardMaterial({
            color: 0x3b8d70,
            roughness: 0.48,
            metalness: 0.05,
          }),
        );
        scene.add(mesh);
        camera.position.set(radius * 1.7, -radius * 2.1, radius * 1.5);
        camera.near = radius / 100;
        camera.far = radius * 30;
        camera.updateProjectionMatrix();
        controls.target.set(0, 0, 0);
        controls.update();
      })
      .catch(() => {
        if (!disposed)
          setError("Could not load the 3D preview. Try the STL download.");
      });
    const render = () => {
      controls.update();
      renderer.render(scene, camera);
      frame = requestAnimationFrame(render);
    };
    render();
    return () => {
      disposed = true;
      controller.abort();
      cancelAnimationFrame(frame);
      observer.disconnect();
      controls.dispose();
      if (mesh) {
        mesh.geometry.dispose();
        (mesh.material as THREE.Material).dispose();
      }
      renderer.dispose();
      renderer.domElement.remove();
    };
  }, [url]);
  return (
    <div>
      <div
        className="viewer"
        ref={host}
        aria-label="Interactive 3D part preview"
      />
      {error ? (
        <p role="status">{error}</p>
      ) : (
        <p className="muted small">
          Drag to rotate / Scroll to zoom / Dimensions in millimetres
        </p>
      )}
    </div>
  );
}
