/**
 * Environment detection utility
 * Detects if running in Electron or web browser
 */

export const isElectron = () => {
  return typeof window !== 'undefined' && window.electronAPI !== undefined;
};

export const isWeb = () => {
  return !isElectron();
};

export const getEnvironment = () => {
  if (isElectron()) {
    return 'electron';
  }
  return 'web';
};

export default {
  isElectron,
  isWeb,
  getEnvironment,
};

