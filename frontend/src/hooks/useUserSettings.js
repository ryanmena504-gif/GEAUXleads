/**
 * Sender information used to sign device-native draft handoffs. The app does
 * not connect to a mail provider or send a message; this only supplies the
 * business details that appear in the draft body.
 */
const DEFAULT_SETTINGS = {
  sender_name: "Ryan Mena",
  sender_email: "ryanmena@theshirtlesshandyman.com",
  sender_phone: "(504) 264-4919",
  email_provider: "apple",
};

export const useUserSettings = () => ({ settings: DEFAULT_SETTINGS });

