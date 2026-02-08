/**
 * AVS Compaction Guard Extension
 *
 * Sauvegarde automatique du contexte vers la base de connaissances AVS
 * avant chaque compaction pour Ã©viter la perte d'informations importantes.
 */

import type { ExtensionAPI } from "@mariozechner/pi-coding-agent";

const AVS_INTRANET_URL = process.env.AVS_INTRANET_URL || "https://intra.avstech.fr";
const AVS_API_KEY = process.env.AVS_API_KEY;

interface KnowledgeNodePayload {
  type: string;
  title: string;
  content: string;
  visibility: "public" | "restricted" | "admin";
}

async function saveToKnowledgeBase(payload: KnowledgeNodePayload): Promise<boolean> {
  if (!AVS_API_KEY) {
    console.warn("[AVS Compaction Guard] AVS_API_KEY not configured, skipping KB save");
    return false;
  }

  try {
    const response = await fetch(`${AVS_INTRANET_URL}/api/external/knowledge/nodes`, {
      method: "POST",
      headers: {
        "X-API-Key": AVS_API_KEY,
        "Content-Type": "application/json; charset=utf-8",
      },
      body: JSON.stringify(payload),
    });

    if (!response.ok) {
      console.warn(
        `[AVS Compaction Guard] KB save failed: ${response.status} ${response.statusText}`,
      );
      return false;
    }

    const result = await response.json();
    console.log(`[AVS Compaction Guard] Context saved to KB: node ${result.id}`);
    return true;
  } catch (error) {
    console.warn(
      `[AVS Compaction Guard] KB save error: ${error instanceof Error ? error.message : String(error)}`,
    );
    return false;
  }
}

async function sendTelegramAlert(message: string): Promise<void> {
  if (!AVS_API_KEY) {
    return;
  }

  try {
    await fetch(`${AVS_INTRANET_URL}/api/external/michel`, {
      method: "POST",
      headers: {
        "X-API-Key": AVS_API_KEY,
        "Content-Type": "application/json; charset=utf-8",
      },
      body: JSON.stringify({
        message,
        from: "Compaction Guard",
      }),
    });
  } catch {
    // Silent fail for notifications
  }
}

function extractImportantContext(messages: unknown[]): string {
  const important: string[] = [];

  for (const msg of messages) {
    if (!msg || typeof msg !== "object") {
      continue;
    }

    const message = msg as { role?: string; content?: unknown };

    // Extract user messages (requests)
    if (message.role === "user" && message.content) {
      const content = Array.isArray(message.content)
        ? message.content.map((c: { text?: string }) => c.text || "").join(" ")
        : typeof message.content === "string"
          ? message.content
          : JSON.stringify(message.content);

      if (content.length > 50) {
        important.push(`[User] ${content.slice(0, 500)}${content.length > 500 ? "..." : ""}`);
      }
    }

    // Extract assistant decisions/conclusions
    if (message.role === "assistant" && message.content) {
      const content = Array.isArray(message.content)
        ? message.content.map((c: { text?: string }) => c.text || "").join(" ")
        : typeof message.content === "string"
          ? message.content
          : JSON.stringify(message.content);

      // Look for conclusions, decisions, summaries
      const conclusionPatterns = [
        /en rÃ©sumÃ©/i,
        /en conclusion/i,
        /j'ai (crÃ©Ã©|modifiÃ©|ajoutÃ©)/i,
        /voici ce que/i,
        /le problÃ¨me Ã©tait/i,
        /la solution/i,
        /terminÃ©/i,
        /commit/i,
        /deployed/i,
      ];

      for (const pattern of conclusionPatterns) {
        if (pattern.test(content)) {
          important.push(`[Decision] ${content.slice(0, 300)}${content.length > 300 ? "..." : ""}`);
          break;
        }
      }
    }
  }

  return important.slice(-10).join("\n\n"); // Keep last 10 important items
}

export default function avsCompactionGuardExtension(api: ExtensionAPI): void {
  api.on("session_before_compact", async (event) => {
    const { preparation } = event;
    const timestamp = new Date().toISOString().slice(0, 16).replace("T", " ");

    // Extract important context before it's lost
    const allMessages = [
      ...preparation.messagesToSummarize,
      ...(preparation.turnPrefixMessages || []),
    ];

    const importantContext = extractImportantContext(allMessages);
    const { edited, written, read } = preparation.fileOps;

    // Build context summary
    const contextParts: string[] = [];

    if (importantContext) {
      contextParts.push("## Contexte important\n\n" + importantContext);
    }

    if (edited.size > 0 || written.size > 0) {
      const modifiedFiles = [...new Set([...edited, ...written])].toSorted();
      contextParts.push(
        "## Fichiers modifiÃ©s\n\n" + modifiedFiles.map((f) => `- ${f}`).join("\n"),
      );
    }

    if (read.size > 0) {
      const readFiles = [...read].filter((f) => !edited.has(f) && !written.has(f)).toSorted();
      if (readFiles.length > 0) {
        contextParts.push(
          "## Fichiers lus\n\n" +
            readFiles
              .slice(0, 20)
              .map((f) => `- ${f}`)
              .join("\n"),
        );
      }
    }

    if (contextParts.length === 0) {
      console.log("[AVS Compaction Guard] No significant context to save");
      return; // Let default compaction proceed
    }

    const content = contextParts.join("\n\n");

    // Save to KB
    const saved = await saveToKnowledgeBase({
      type: "note",
      title: `Michel Session Backup ${timestamp}`,
      content: `Auto-saved before compaction.\n\n${content}`,
      visibility: "admin",
    });

    // Send notification
    if (saved) {
      await sendTelegramAlert(
        `ðŸ“¦ Compaction en cours. Contexte sauvegardÃ© dans la KB (${allMessages.length} messages rÃ©sumÃ©s).`,
      );
    } else {
      await sendTelegramAlert(
        `âš ï¸ Compaction en cours mais sauvegarde KB Ã©chouÃ©e. ${allMessages.length} messages vont Ãªtre rÃ©sumÃ©s.`,
      );
    }

    // Return undefined to let the default compaction-safeguard handle the actual summarization
    return undefined;
  });

  console.log("[AVS Compaction Guard] Extension loaded");
}
