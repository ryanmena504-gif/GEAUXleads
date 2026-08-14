import React from "react";
import clsx from "clsx";
import {
  Phone,
  MessageSquare,
  Mail,
  Search,
  MapPin,
  FileText,
  Users,
  RotateCw,
  Clock,
} from "lucide-react";

const cfg = {
  "Call Today": { icon: Phone, color: "text-emerald-400", bg: "bg-emerald-500/10 border-emerald-500/25" },
  "Send Text": { icon: MessageSquare, color: "text-sky-300", bg: "bg-sky-500/10 border-sky-500/25" },
  "Send Email": { icon: Mail, color: "text-blue-300", bg: "bg-blue-500/10 border-blue-500/25" },
  "Research First": { icon: Search, color: "text-amber-300", bg: "bg-amber-500/10 border-amber-500/25" },
  "Visit Property": { icon: MapPin, color: "text-orange-300", bg: "bg-orange-500/10 border-orange-500/25" },
  "Prepare Estimate": { icon: FileText, color: "text-violet-300", bg: "bg-violet-500/10 border-violet-500/25" },
  "Ask for Referral": { icon: Users, color: "text-fuchsia-300", bg: "bg-fuchsia-500/10 border-fuchsia-500/25" },
  "Follow Up": { icon: RotateCw, color: "text-indigo-300", bg: "bg-indigo-500/10 border-indigo-500/25" },
  Wait: { icon: Clock, color: "text-neutral-400", bg: "bg-neutral-500/10 border-neutral-500/25" },
};

export const MissionBadge = ({ mission, className, size = "md" }) => {
  const c = cfg[mission] || cfg.Wait;
  const Icon = c.icon;
  const sz = size === "sm" ? "text-[10px] px-1.5 py-0.5" : "text-[11px] px-2 py-1";
  return (
    <span
      data-testid={`mission-badge-${mission}`}
      className={clsx(
        "inline-flex items-center gap-1.5 rounded border font-medium",
        c.bg,
        c.color,
        sz,
        className,
      )}
    >
      <Icon size={size === "sm" ? 10 : 12} strokeWidth={2.25} />
      {mission}
    </span>
  );
};

export default MissionBadge;
