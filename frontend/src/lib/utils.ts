export function getErrorMessage(err: unknown, fallback: string): string {
  if (err && typeof err === 'object' && 'response' in err) {
    const axiosErr = err as {
      response?: { data?: { error?: { message?: string }; detail?: string } };
    };
    return axiosErr?.response?.data?.error?.message || axiosErr?.response?.data?.detail || fallback;
  }
  return fallback;
}
