import { useSyncExternalStore } from "react";

const QUEUE_PATH = "/review";
const STORAGE_KEY = "larkfield.reviewQueuePath";

function isQueuePath(path: string | null): path is string {
  return path === QUEUE_PATH || Boolean(path?.startsWith(`${QUEUE_PATH}?`));
}

export function rememberQueuePath(search: string) {
  try {
    sessionStorage.setItem(STORAGE_KEY, search ? `${QUEUE_PATH}?${search}` : QUEUE_PATH);
  } catch {
    // storage blocked: the way back is the bare queue
  }
}

export function getQueuePath(): string {
  try {
    const path = sessionStorage.getItem(STORAGE_KEY);
    return isQueuePath(path) ? path : QUEUE_PATH;
  } catch {
    return QUEUE_PATH;
  }
}

const neverChanges = () => () => {};

export function useQueuePath(): string {
  return useSyncExternalStore(neverChanges, getQueuePath, () => QUEUE_PATH);
}
