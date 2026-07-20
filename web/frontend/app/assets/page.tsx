import fs from "fs";
import path from "path";
import Link from "next/link";

interface AssetFile {
  name: string;
  size: string;
  isDir: boolean;
}

function formatSize(bytes: number): string {
  if (bytes === 0) return "0 B";
  const units = ["B", "KB", "MB", "GB"];
  const i = Math.floor(Math.log(bytes) / Math.log(1024));
  return `${(bytes / Math.pow(1024, i)).toFixed(i === 0 ? 0 : 1)} ${units[i]}`;
}

export default function AssetsPage() {
  const assetsDir = path.join(process.cwd(), "public", "assets");
  let files: AssetFile[] = [];

  try {
    const entries = fs.readdirSync(assetsDir, { withFileTypes: true });
    files = entries
      .filter((e) => e.name !== ".gitkeep")
      .map((e) => {
        const fullPath = path.join(assetsDir, e.name);
        const stat = fs.statSync(fullPath);
        return {
          name: e.name,
          size: e.isDirectory() ? "-" : formatSize(stat.size),
          isDir: e.isDirectory(),
        };
      })
      .sort((a, b) => {
        if (a.isDir !== b.isDir) return a.isDir ? -1 : 1;
        return a.name.localeCompare(b.name);
      });
  } catch {
    // assets dir doesn't exist or can't be read
  }

  return (
    <div>
      <h1 className="text-xl font-bold mb-4">Assets</h1>
      {files.length === 0 ? (
        <p className="text-muted text-sm">No assets found.</p>
      ) : (
        <div className="card overflow-hidden">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-border text-muted text-left">
                <th className="p-3 font-medium">Name</th>
                <th className="p-3 font-medium w-24 text-right">Size</th>
              </tr>
            </thead>
            <tbody>
              {files.map((f) => (
                <tr
                  key={f.name}
                  className="border-b border-border/50 last:border-0 hover:bg-surface/80"
                >
                  <td className="p-3">
                    {f.isDir ? (
                      <span className="text-muted">{f.name}/</span>
                    ) : (
                      <Link
                        href={`/assets/${f.name}`}
                        className="hover:text-brand transition-colors"
                        target="_blank"
                      >
                        {f.name}
                      </Link>
                    )}
                  </td>
                  <td className="p-3 text-right text-muted font-mono text-xs">
                    {f.size}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
