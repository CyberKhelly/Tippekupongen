import { Info } from "lucide-react";

export default function OmPage() {
  return (
    <div className="min-h-screen bg-[#0D0D0D] flex items-center justify-center">
      <div className="text-center">
        <div className="flex items-center justify-center w-12 h-12 rounded-xl bg-[#1C1C1C] border border-[rgba(255,255,255,0.07)] mx-auto mb-4">
          <Info size={20} strokeWidth={1.75} className="text-[#4A4744]" />
        </div>
        <p className="text-[13px] font-semibold text-[#E8E4DD]">Om TippeIQ</p>
        <p className="text-[12px] text-[#4A4744] mt-1">Under planlegging</p>
      </div>
    </div>
  );
}
