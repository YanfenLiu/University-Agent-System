import type { Competition } from "../../../services/competitions";
import type { UserProfile } from "../types";

/**
 * 根据用户画像对竞赛进行排序推荐
 * 匹配度高的竞赛排在前面
 */
export function recommendCompetitions(
  competitions: Competition[],
  userProfile: UserProfile,
): Competition[] {
  if (!userProfile.matched || !userProfile.major) {
    return competitions;
  }

  return [...competitions].sort((a, b) => {
    const aRelevance = a.tags.some(
      (t) =>
        t.includes(userProfile.major) ||
        userProfile.interests.some((i) => t.includes(i)),
    )
      ? 1
      : 0;
    const bRelevance = b.tags.some(
      (t) =>
        t.includes(userProfile.major) ||
        userProfile.interests.some((i) => t.includes(i)),
    )
      ? 1
      : 0;
    return bRelevance - aRelevance;
  });
}
