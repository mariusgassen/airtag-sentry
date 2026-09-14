import type { ComponentType } from 'react'
import { KeyIcon } from './components/icons'
import type { DeviceIconName } from './deviceIcons'
import {
  AirpodsCaseIcon,
  AirpodsIcon,
  AirpodsLeftIcon,
  AirpodsRightIcon,
  BackpackIcon,
  BikeIcon,
  BookIcon,
  BoxIcon,
  CameraIcon,
  CarIcon,
  HeadphonesIcon,
  IphoneIcon,
  LaptopIcon,
  MacIcon,
  PetIcon,
  SuitcaseIcon,
  WalletIcon,
  WatchIcon,
} from './deviceIcons'

export const DEVICE_ICON_NAMES: DeviceIconName[] = [
  'bike',
  'backpack',
  'car',
  'keys',
  'wallet',
  'suitcase',
  'laptop',
  'camera',
  'pet',
  'headphones',
  'book',
  'box',
  'iphone',
  'airpods',
  'airpods-left',
  'airpods-right',
  'airpods-case',
  'watch',
  'mac',
]

export const DEVICE_ICON_COMPONENTS: Record<DeviceIconName, ComponentType<{ className?: string }>> = {
  bike: BikeIcon,
  backpack: BackpackIcon,
  car: CarIcon,
  keys: KeyIcon,
  wallet: WalletIcon,
  suitcase: SuitcaseIcon,
  laptop: LaptopIcon,
  camera: CameraIcon,
  pet: PetIcon,
  headphones: HeadphonesIcon,
  book: BookIcon,
  box: BoxIcon,
  iphone: IphoneIcon,
  airpods: AirpodsIcon,
  'airpods-left': AirpodsLeftIcon,
  'airpods-right': AirpodsRightIcon,
  'airpods-case': AirpodsCaseIcon,
  watch: WatchIcon,
  mac: MacIcon,
}

export const DEVICE_ICON_LABELS: Record<DeviceIconName, string> = {
  bike: 'Fahrrad',
  backpack: 'Rucksack',
  car: 'Auto',
  keys: 'Schlüssel',
  wallet: 'Geldbeutel',
  suitcase: 'Koffer',
  laptop: 'Laptop',
  camera: 'Kamera',
  pet: 'Haustier',
  headphones: 'Kopfhörer',
  book: 'Buch',
  box: 'Paket',
  iphone: 'iPhone',
  airpods: 'AirPods',
  'airpods-left': 'AirPod links',
  'airpods-right': 'AirPod rechts',
  'airpods-case': 'AirPods-Hülle',
  watch: 'Apple Watch',
  mac: 'Mac',
}

/** Default icon for an owner device that has no manually-picked one, derived
 * from pyicloud's `device_type` (currently "iPhone" / "iPad" / "Mac" /
 * "Watch" - see owner_tracking.py). "Mac" alone doesn't say laptop vs.
 * desktop, so a MacBook is told apart by name; every other Mac (Mac Studio,
 * iMac, Mac mini, Mac Pro, ...) gets the desktop glyph. Returns null for a
 * type with no good match (e.g. iPad) so callers fall back to the existing
 * generic-person look instead of a wrong-looking guess. */
export function defaultDeviceIcon(deviceType: string, name: string): DeviceIconName | null {
  switch (deviceType) {
    case 'iPhone':
      return 'iphone'
    case 'Watch':
      return 'watch'
    case 'Mac':
      return /macbook/i.test(name) ? 'laptop' : 'mac'
    default:
      return null
  }
}
