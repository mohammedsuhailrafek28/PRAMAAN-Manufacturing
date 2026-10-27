import { cpSync } from "node:fs";
cpSync("dist", process.argv[2], { recursive: true, force: true });
