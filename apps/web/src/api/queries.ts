import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "./client";

export const queryKeys = { jobs: ["jobs"] as const, job: (id: string) => ["jobs", id] as const, reviews: ["reviews"] as const, models: ["models"] as const, evidence: ["evidence"] as const };

export function useJobs() { return useQuery({ queryKey: queryKeys.jobs, queryFn: ({ signal }) => api.listJobs(signal), refetchInterval: (query) => query.state.data?.items.some((job) => job.status === "QUEUED" || job.status === "RUNNING") ? 3_000 : false }); }
export function useJob(id: string) { return useQuery({ queryKey: queryKeys.job(id), queryFn: ({ signal }) => api.getJob(id, signal), refetchInterval: (query) => { const status = query.state.data?.status; return status === "QUEUED" || status === "RUNNING" ? (document.hidden ? 10_000 : 2_000) : false; } }); }
export function useCreateJob() { const client = useQueryClient(); return useMutation({ mutationFn: ({ category, files }: { category: string; files: File[] }) => api.createJob(category, files), onSuccess: async () => client.invalidateQueries({ queryKey: queryKeys.jobs }) }); }
export function useReviews() { return useQuery({ queryKey: queryKeys.reviews, queryFn: ({ signal }) => api.listReviews(signal) }); }
export function useModels() { return useQuery({ queryKey: queryKeys.models, queryFn: ({ signal }) => api.listModels(signal) }); }
export function useEvidence() { return useQuery({ queryKey: queryKeys.evidence, queryFn: ({ signal }) => api.getEvidence(signal) }); }
