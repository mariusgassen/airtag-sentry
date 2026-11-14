import {
  appleCancelLogin,
  appleDisconnect,
  appleImportSession,
  appleLogin,
  appleSelectTwoFactorMethod,
  appleSubmitTwoFactorCode,
  getAppleStatus,
  getOwnerAppleStatus,
  ownerAppleCancelLogin,
  ownerAppleDisconnect,
  ownerAppleLogin,
  ownerAppleSetIncludeFamily,
  ownerAppleSubmitTwoFactorCode,
} from '../api'
import type { AppleConnectAdapter } from './AppleConnectPanel'
import { AppleConnectPanel } from './AppleConnectPanel'
import { OwnerDevicesPanel } from './OwnerDevicesPanel'

const AIRTAG_APPLE_ADAPTER: AppleConnectAdapter = {
  getStatus: getAppleStatus,
  login: appleLogin,
  importSession: appleImportSession,
  selectMethod: appleSelectTwoFactorMethod,
  submitCode: appleSubmitTwoFactorCode,
  cancelLogin: appleCancelLogin,
  disconnect: appleDisconnect,
}

const OWNER_APPLE_ADAPTER: AppleConnectAdapter = {
  getStatus: getOwnerAppleStatus,
  login: ownerAppleLogin,
  submitCode: ownerAppleSubmitTwoFactorCode,
  cancelLogin: ownerAppleCancelLogin,
  disconnect: ownerAppleDisconnect,
  familySharingToggle: true,
  setFamilySharing: ownerAppleSetIncludeFamily,
}

export function SettingsAppleAccounts() {
  return (
    <>
      <div className="px-3">
        <AppleConnectPanel title="AirTag-Tracking" adapter={AIRTAG_APPLE_ADAPTER} />
        <AppleConnectPanel title="Eigener Standort (optional)" adapter={OWNER_APPLE_ADAPTER} />
      </div>
      <OwnerDevicesPanel />
    </>
  )
}
