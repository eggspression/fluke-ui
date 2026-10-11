import { HttpErrorResponse } from '@angular/common/http';

export function requestMessage(error: HttpErrorResponse): string {
  if (error.status === 0) return 'Cannot reach the API. Check that it is running.';
  if (error.status === 401) return 'Your login expired. Sign in again.';
  if (error.status === 404) return 'This record is unavailable.';
  if (error.status === 409) return 'This experiment already has runs. Create a new experiment to change settings.';
  if (typeof error.error?.detail === 'string') return error.error.detail;
  return 'The request failed. Please try again.';
}

export function fieldMessages(error: HttpErrorResponse): Record<string, string> {
  const messages: Record<string, string> = {};
  if (error.status !== 422 || !Array.isArray(error.error?.detail)) return messages;
  for (const issue of error.error.detail) {
    const field = issue.loc?.findLast((part: unknown) => typeof part === 'string' && part !== 'body');
    if (typeof field === 'string') messages[field] = issue.msg;
  }
  return messages;
}
