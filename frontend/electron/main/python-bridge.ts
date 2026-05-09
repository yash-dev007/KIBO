import { app } from "electron";
import { spawn, type ChildProcessWithoutNullStreams } from "node:child_process";
import { existsSync } from "node:fs";
import { join } from "node:path";

const DEFAULT_BACKEND_URL = "http://127.0.0.1:8765";
const HEALTH_TIMEOUT_MS = 1000;
const STARTUP_TIMEOUT_MS = 30000;
const POLL_INTERVAL_MS = 300;

export class PythonBridge {
  private process: ChildProcessWithoutNullStreams | null = null;
  private ready = false;
  private readonly backendUrl = process.env.KIBO_BACKEND_URL ?? DEFAULT_BACKEND_URL;

  start(): void {
    if (this.process || process.env.KIBO_SKIP_PYTHON_BRIDGE === "1") {
      return;
    }

    const command = this.command();
    this.process = spawn(command.executable, command.args, {
      cwd: command.cwd,
      env: { ...process.env, KIBO_API_HOST: "127.0.0.1", KIBO_API_PORT: "8765" },
      windowsHide: true,
    });

    this.process.once("exit", () => {
      this.process = null;
      this.ready = false;
    });
  }

  async waitUntilReady(timeoutMs = STARTUP_TIMEOUT_MS): Promise<boolean> {
    const startedAt = Date.now();
    while (Date.now() - startedAt < timeoutMs) {
      if (await this.health()) {
        this.ready = true;
        return true;
      }
      await new Promise((resolve) => setTimeout(resolve, POLL_INTERVAL_MS));
    }
    return false;
  }

  async health(): Promise<boolean> {
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), HEALTH_TIMEOUT_MS);
    try {
      const response = await fetch(`${this.backendUrl}/health`, {
        signal: controller.signal,
      });
      return response.ok;
    } catch {
      return false;
    } finally {
      clearTimeout(timeout);
    }
  }

  stop(): void {
    if (!this.process) {
      return;
    }

    this.process.kill();
    this.process = null;
  }

  status(): { running: boolean; url: string } {
    return {
      running: this.process !== null || this.ready,
      url: this.backendUrl,
    };
  }

  private command(): { executable: string; args: string[]; cwd: string } {
    if (app.isPackaged) {
      const backendExe = join(process.resourcesPath, "python_backend", "server.exe");
      if (existsSync(backendExe)) {
        return {
          executable: backendExe,
          args: [],
          cwd: join(process.resourcesPath, "python_backend"),
        };
      }
    }

    const repoRoot = join(app.getAppPath(), "..");
    return {
      executable: "python",
      args: ["-m", "src.api.main"],
      cwd: repoRoot,
    };
  }
}
