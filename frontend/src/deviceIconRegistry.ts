import type { ComponentType } from 'react'
import { KeyIcon } from './components/icons'
import type { DeviceIconName } from './deviceIcons'
import {
  AirpodsIcon,
  BackpackIcon,
  BikeIcon,
  BookIcon,
  BoxIcon,
  CameraIcon,
  CarIcon,
  HeadphonesIcon,
  IphoneIcon,
  LaptopIcon,
  PetIcon,
  SuitcaseIcon,
  WalletIcon,
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
}
