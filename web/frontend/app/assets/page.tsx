import fs from "fs";
import path from "path";
import Link from "next/link";

interface TreeNode {
  name: string;
  relPath: string;
  size: string;
  isDir: boolean;
  children: TreeNode[];
}

function formatSize(bytes: number): string {
  if (bytes === 0) return "0 B";
  const units = ["B", "KB", "MB", "GB"];
  const i = Math.floor(Math.log(bytes) / Math.log(1024));
  return `${(bytes / Math.pow(1024, i)).toFixed(i === 0 ? 0 : 1)} ${units[i]}`;
}

function buildTree(dir: string, prefix: string = ""): TreeNode[] {
  const nodes: TreeNode[] = [];
  try {
    const entries = fs.readdirSync(dir, { withFileTypes: true });
    for (const e of entries) {
      if (e.name === ".gitkeep") continue;
      const fullPath = path.join(dir, e.name);
      const relPath = prefix ? `${prefix}/${e.name}` : e.name;
      if (e.isDirectory()) {
        nodes.push({
          name: e.name,
          relPath,
          size: "-",
          isDir: true,
          children: buildTree(fullPath, relPath),
        });
      } else {
        const stat = fs.statSync(fullPath);
        nodes.push({
          name: e.name,
          relPath,
          size: formatSize(stat.size),
          isDir: false,
          children: [],
        });
      }
    }
  } catch {
    // skip
  }
  nodes.sort((a, b) => {
    if (a.isDir !== b.isDir) return a.isDir ? -1 : 1;
    return a.name.localeCompare(b.name);
  });
  return nodes;
}

function TreeView({ nodes, depth }: { nodes: TreeNode[]; depth: number }) {
  return (
    <ul className="list-none m-0 p-0">
      {nodes.map((n) => (
        <li key={n.relPath}>
          <div
            className="flex items-center gap-2 py-0.5 text-sm"
            style={{ paddingLeft: `${depth * 1.25}rem` }}
          >
            <span className="text-muted w-4 shrink-0">
              {n.isDir ? "📁" : "📄"}
            </span>
            {n.isDir ? (
              <span className="font-medium text-muted">{n.name}/</span>
            ) : (
              <Link
                href={`/assets/${n.relPath}`}
                target="_blank"
                className="hover:text-brand transition-colors"
              >
                {n.name}
              </Link>
            )}
            <span className="text-muted/60 font-mono text-xs ml-auto tabular-nums">
              {n.size}
            </span>
          </div>
          {n.isDir && n.children.length > 0 && (
            <TreeView nodes={n.children} depth={depth + 1} />
          )}
        </li>
      ))}
    </ul>
  );
}

export const dynamic = "force-dynamic";

export default function AssetsPage() {
  const assetsDir = path.join(process.cwd(), "public", "assets");
  const tree = buildTree(assetsDir);

  return (
    <div>
      <h1 className="text-xl font-bold mb-4">Assets</h1>
      {tree.length === 0 ? (
        <p className="text-muted text-sm">No assets found.</p>
      ) : (
        <div className="card p-3">
          <TreeView nodes={tree} depth={0} />
        </div>
      )}
    </div>
  );
}
