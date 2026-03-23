/**
 * Desktop Indicator Component
 * Shows desktop-specific UI elements when running in Electron
 */

import { useEffect, useState } from 'react';
import { isElectron, electronAPI } from '../utils/electron-api';

const DesktopIndicator = () => {
  const [isDesktop, setIsDesktop] = useState(false);
  const [monitoringStatus, setMonitoringStatus] = useState(null);

  useEffect(() => {
    const checkDesktop = async () => {
      if (isElectron()) {
        setIsDesktop(true);
        // Load monitoring status
        try {
          const status = await electronAPI.getMonitoringStatus();
          setMonitoringStatus(status);
        } catch (error) {
          console.error('Failed to get monitoring status:', error);
        }
      }
    };
    checkDesktop();
  }, []);

  if (!isDesktop) {
    return null;
  }

  return (
    <div className="desktop-indicator">
      {/* Desktop-specific UI elements can be added here */}
      {monitoringStatus && (
        <div className="monitoring-status">
          {monitoringStatus.isMonitoring ? (
            <span className="status-active">● Monitoring Active</span>
          ) : (
            <span className="status-inactive">○ Monitoring Stopped</span>
          )}
        </div>
      )}
    </div>
  );
};

export default DesktopIndicator;

