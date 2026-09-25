import React, { useState } from "react";
import { FileMeta, FolderMeta } from "../lib/api";

type FileTreeProps = {
  files: FileMeta[];
  folders: FolderMeta[];
  activeFileId: number | null;
  activeFolderId: number | null;
  onSelectFile: (file: FileMeta) => void;
  onSelectFolder: (folder: FolderMeta) => void;
  onRename: (type: "file" | "folder", item: FileMeta | FolderMeta) => void;
  presence: Record<number, number>;
};

export default function FileTree({ files, folders, activeFileId, activeFolderId, onSelectFile, onSelectFolder, onRename, presence }: FileTreeProps) {
  return (
    <div className="file-tree-container">
      <TreeItem
        parentId={null}
        files={files || []}
        folders={folders || []}
        activeFileId={activeFileId}
        activeFolderId={activeFolderId}
        onSelectFile={onSelectFile}
        onSelectFolder={onSelectFolder}
        onRename={onRename}
        presence={presence || {}}
        visited={new Set()}
      />
    </div>
  );
}

function TreeItem({
  parentId,
  files,
  folders,
  activeFileId,
  activeFolderId,
  onSelectFile,
  onSelectFolder,
  onRename,
  presence,
  visited
}: {
  parentId: number | null;
  files: FileMeta[];
  folders: FolderMeta[];
  activeFileId: number | null;
  activeFolderId: number | null;
  onSelectFile: (file: FileMeta) => void;
  onSelectFolder: (folder: FolderMeta) => void;
  onRename: (type: "file" | "folder", item: FileMeta | FolderMeta) => void;
  presence: Record<number, number>;
  visited: Set<number>;
}) {
  const childFolders = (folders || []).filter(f => f.parent_folder_id === parentId);
  const childFiles = (files || []).filter(f => f.folder_id === parentId);

  // If we are at the root, also find "orphan" folders (folders whose parent is not in the list)
  // and render them here so they don't disappear.
  let orphanFolders: FolderMeta[] = [];
  if (parentId === null) {
    const allParentIds = new Set(folders.map(f => f.parent_folder_id).filter(Boolean));
    orphanFolders = folders.filter(f => f.parent_folder_id !== null && !allParentIds.has(f.parent_folder_id));
    // This is a bit simplistic; it doesn't check if the parent is actually missing from the DB,
    // but it prevents folders from disappearing if their parent is missing from the current list.
    // Actually, a better way is to check if the parent_folder_id is not present in the folders list.
    const existingIds = new Set(folders.map(f => f.id));
    orphanFolders = folders.filter(f => f.parent_folder_id !== null && !existingIds.has(f.parent_folder_id));
  }

  return (
    <div className="tree-item" style={{ display: "flex", flexDirection: "column", gap: 2 }}>
      {childFolders.map(folder => (
        <FolderItem
          key={folder.id}
          folder={folder}
          files={files}
          folders={folders}
          activeFileId={activeFileId}
          activeFolderId={activeFolderId}
          onSelectFile={onSelectFile}
          onSelectFolder={onSelectFolder}
          onRename={onRename}
          presence={presence}
          visited={visited}
        />
      ))}
      {orphanFolders.map(folder => (
        <FolderItem
          key={`orphan-${folder.id}`}
          folder={folder}
          files={files}
          folders={folders}
          activeFileId={activeFileId}
          activeFolderId={activeFolderId}
          onSelectFile={onSelectFile}
          onSelectFolder={onSelectFolder}
          onRename={onRename}
          presence={presence}
          visited={visited}
        />
      ))}
      {childFiles.map(file => {
        const usersOnFile = Object.entries(presence || {}).filter(([_, fId]) => fId === file.id);
        return (
          <div
            key={file.id}
            className={`file-node ${file.id === activeFileId ? "active" : ""}`}
            onClick={() => onSelectFile(file)}
            onDoubleClick={() => onRename("file", file)}
            style={{
              cursor: "pointer",
              display: "flex",
              alignItems: "center",
              gap: 4,
              padding: "2px 4px",
              borderRadius: 3,
              backgroundColor: file.id === activeFileId ? "rgba(88,166,255,0.2)" : "transparent",
              color: "var(--fg)"
            }}
          >
            <span style={{ display: "flex", alignItems: "center", gap: 4 }}>
              📄 {file.path ? file.path.split("/").pop() : "untitled"}
              {usersOnFile.length > 0 && (
                <span className="presence-count" style={{ fontSize: 10, background: "var(--accent)", color: "white", borderRadius: 8, padding: "0 4px" }}>
                  {usersOnFile.length}
                </span>
              )}
            </span>
          </div>
        );
      })}
    </div>
  );
}

function FolderItem({
  folder,
  files,
  folders,
  activeFileId,
  activeFolderId,
  onSelectFile,
  onSelectFolder,
  onRename,
  presence,
  visited
}: {
  folder: FolderMeta;
  files: FileMeta[];
  folders: FolderMeta[];
  activeFileId: number | null;
  activeFolderId: number | null;
  onSelectFile: (file: FileMeta) => void;
  onSelectFolder: (folder: FolderMeta) => void;
  onRename: (type: "file" | "folder", item: FileMeta | FolderMeta) => void;
  presence: Record<number, number>;
  visited: Set<number>;
}) {
  const [isOpen, setIsOpen] = useState(true);

  if (visited.has(folder.id)) {
    return (
      <div className="folder-node" style={{ opacity: 0.5, fontSize: 11 }}>
        📁 {folder.name} (Cycle detected)
      </div>
    );
  }

  const nextVisited = new Set(visited).add(folder.id);

  return (
    <div className="folder-node">
      <div
        className={`folder-header ${folder.id === activeFolderId ? "active" : ""}`}
        onClick={() => {
          setIsOpen(!isOpen);
          onSelectFolder(folder);
        }}
        onDoubleClick={() => onRename("folder", folder)}
        style={{ cursor: "pointer", display: "flex", alignItems: "center", gap: 4 }}
      >
        <span>{isOpen ? "▼" : "▶"}</span>
        <span className="folder-name">📁 {folder.name}</span>
      </div>
      {isOpen && (
        <div className="folder-children" style={{ paddingLeft: 16 }}>
          <TreeItem
            parentId={folder.id}
            files={files}
            folders={folders}
            activeFileId={activeFileId}
            activeFolderId={activeFolderId}
            onSelectFile={onSelectFile}
            onSelectFolder={onSelectFolder}
            onRename={onRename}
            presence={presence}
            visited={nextVisited}
          />
        </div>
      )}
    </div>
  );
}
