"use client";

import { useState, useEffect } from "react";
import { useQuery } from "@tanstack/react-query";
import { getCoupons } from "@/lib/api";
import type { CouponListItem } from "@/lib/types";

export function useCouponQuery() {
  const [refetchMs, setRefetchMs] = useState<number | false>(false);
  const [selectedCouponId, setSelectedCouponId] = useState<string | null>(null);

  const couponsQuery = useQuery({
    queryKey: ["coupons"],
    queryFn: () => getCoupons(),
    staleTime: 5 * 60_000,
    retry: 1,
    refetchInterval: refetchMs,
  });

  // Auto-recover: poll every 30 s when in error so the page heals itself
  useEffect(() => {
    setRefetchMs(couponsQuery.isError ? 30_000 : false);
  }, [couponsQuery.isError]);

  // Auto-select first coupon when data arrives
  useEffect(() => {
    if (couponsQuery.data?.length && !selectedCouponId) {
      setSelectedCouponId(couponsQuery.data[0].coupon_id);
    }
  }, [couponsQuery.data, selectedCouponId]);

  return {
    coupons: (couponsQuery.data ?? []) as CouponListItem[],
    selectedCouponId,
    setSelectedCouponId,
    isApiOffline: couponsQuery.isError,
    isCouponsLoading: couponsQuery.isLoading,
  };
}
