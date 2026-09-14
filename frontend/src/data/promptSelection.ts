export function readPromptMode(conversationId: string): string {
  try {
    return localStorage.getItem(`private-chat:prompt-mode:v1:${conversationId}`) ?? 'standard'
  } catch {
    return 'standard'
  }
}
