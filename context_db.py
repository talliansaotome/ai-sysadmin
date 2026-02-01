#!/usr/bin/env python3
"""
Context Database - Store and retrieve system context using ChromaDB for RAG
"""

import json
import os
from typing import Dict, List, Any, Optional, Set
from datetime import datetime, timezone
from pathlib import Path

# Set environment variable BEFORE importing chromadb to prevent .env file reading and disable telemetry
os.environ["CHROMA_ENV_FILE"] = ""
os.environ["ANONYMIZED_TELEMETRY"] = "False"
os.environ["CHROMA_TELEMETRY_ENABLED"] = "False"

import chromadb
from chromadb.config import Settings


class ContextDatabase:
    """Manage system context and relationships in ChromaDB"""
    
    def __init__(
        self,
        host: str = "localhost",
        port: int = 8000,
        persist_directory: str = "/var/lib/chromadb"
    ):
        """Initialize ChromaDB client"""
        
        self.client = chromadb.HttpClient(
            host=host,
            port=port,
            settings=Settings(
                anonymized_telemetry=False,
                allow_reset=False,
                chroma_telemetry_enabled=False
            )
        )
        
        # Create or get collections
        self.systems_collection = self.client.get_or_create_collection(
            name="systems",
            metadata={"description": "System definitions and metadata"}
        )
        
        self.relationships_collection = self.client.get_or_create_collection(
            name="relationships",
            metadata={"description": "System relationships and dependencies"}
        )
        
        self.issues_collection = self.client.get_or_create_collection(
            name="issues",
            metadata={"description": "Issue tracking and resolution history"}
        )
        
        self.decisions_collection = self.client.get_or_create_collection(
            name="decisions",
            metadata={"description": "AI decisions and outcomes"}
        )
        
        self.config_files_collection = self.client.get_or_create_collection(
            name="config_files",
            metadata={"description": "NixOS configuration files for RAG"}
        )
        
        self.knowledge_collection = self.client.get_or_create_collection(
            name="knowledge",
            metadata={"description": "Operational knowledge: commands, patterns, best practices"}
        )
    
    # ============ System Registry ============
    
    def register_system(
        self,
        hostname: str,
        system_type: str,
        services: List[str],
        capabilities: List[str] = None,
        metadata: Dict[str, Any] = None,
        config_repo: str = None,
        config_branch: str = None,
        os_type: str = "nixos"
    ):
        """Register a system in the database
        
        Args:
            hostname: FQDN of the system
            system_type: Role (e.g., 'workstation', 'server')
            services: List of running services
            capabilities: System capabilities
            metadata: Additional metadata
            config_repo: Git repository URL
            config_branch: Git branch name
            os_type: Operating system (e.g., 'nixos', 'ubuntu', 'debian', 'arch', 'windows', 'macos')
        """
        doc_parts = [
            f"System: {hostname}",
            f"Type: {system_type}",
            f"OS: {os_type}",
            f"Services: {', '.join(services)}",
            f"Capabilities: {', '.join(capabilities or [])}"
        ]
        
        if config_repo:
            doc_parts.append(f"Configuration Repository: {config_repo}")
        if config_branch:
            doc_parts.append(f"Configuration Branch: {config_branch}")
        
        doc = "\n".join(doc_parts)
        
        metadata_dict = {
            "hostname": hostname,
            "type": system_type,
            "os_type": os_type,
            "services": json.dumps(services),
            "capabilities": json.dumps(capabilities or []),
            "metadata": json.dumps(metadata or {}),
            "config_repo": config_repo or "",
            "config_branch": config_branch or "",
            "updated_at": datetime.now(timezone.utc).isoformat()
        }
        
        self.systems_collection.upsert(
            ids=[hostname],
            documents=[doc],
            metadatas=[metadata_dict]
        )
    
    def get_system(self, hostname: str) -> Optional[Dict[str, Any]]:
        """Get system information"""
        try:
            result = self.systems_collection.get(
                ids=[hostname],
                include=["metadatas", "documents"]
            )
            
            if result['ids']:
                metadata = result['metadatas'][0]
                return {
                    "hostname": metadata["hostname"],
                    "type": metadata["type"],
                    "services": json.loads(metadata["services"]),
                    "capabilities": json.loads(metadata["capabilities"]),
                    "metadata": json.loads(metadata["metadata"]),
                    "document": result['documents'][0]
                }
        except:
            pass
        
        return None
    
    def get_all_systems(self) -> List[Dict[str, Any]]:
        """Get all registered systems"""
        result = self.systems_collection.get(include=["metadatas"])
        
        systems = []
        for metadata in result['metadatas']:
            systems.append({
                "hostname": metadata["hostname"],
                "type": metadata["type"],
                "os_type": metadata.get("os_type", "unknown"),
                "services": json.loads(metadata["services"]),
                "capabilities": json.loads(metadata["capabilities"]),
                "config_repo": metadata.get("config_repo", ""),
                "config_branch": metadata.get("config_branch", "")
            })
        
        return systems
    
    def is_system_known(self, hostname: str) -> bool:
        """Check if a system is already registered"""
        try:
            result = self.systems_collection.get(ids=[hostname])
            return len(result['ids']) > 0
        except:
            return False
    
    def get_known_hostnames(self) -> Set[str]:
        """Get set of all known system hostnames"""
        result = self.systems_collection.get(include=["metadatas"])
        return set(metadata["hostname"] for metadata in result['metadatas'])
    
    # ============ Relationships ============
    
    def add_relationship(
        self,
        source: str,
        target: str,
        relationship_type: str,
        description: str = ""
    ):
        """Add a relationship between systems"""
        rel_id = f"{source}→{target}:{relationship_type}"
        doc = f"{source} {relationship_type} {target}. {description}"
        
        self.relationships_collection.upsert(
            ids=[rel_id],
            documents=[doc],
            metadatas=[{
                "source": source,
                "target": target,
                "type": relationship_type,
                "description": description,
                "created_at": datetime.now(timezone.utc).isoformat()
            }]
        )
    
    def get_dependencies(self, hostname: str) -> List[Dict[str, Any]]:
        """Get what a system depends on"""
        result = self.relationships_collection.get(
            where={"source": hostname},
            include=["metadatas"]
        )
        
        return [
            {
                "target": m["target"],
                "type": m["type"],
                "description": m.get("description", "")
            }
            for m in result['metadatas']
        ]
    
    def get_dependents(self, hostname: str) -> List[Dict[str, Any]]:
        """Get what depends on a system"""
        result = self.relationships_collection.get(
            where={"target": hostname},
            include=["metadatas"]
        )
        
        return [
            {
                "source": m["source"],
                "type": m["type"],
                "description": m.get("description", "")
            }
            for m in result['metadatas']
        ]
    
    # ============ Issue History ============
    
    def store_issue(
        self,
        system: str,
        issue_description: str,
        resolution: str = "",
        severity: str = "unknown",
        metadata: Dict[str, Any] = None
    ) -> str:
        """Store an issue and its resolution"""
        issue_id = f"{system}_{datetime.now(timezone.utc).timestamp()}"
        
        doc = f"""
System: {system}
Issue: {issue_description}
Resolution: {resolution}
Severity: {severity}
"""
        
        self.issues_collection.add(
            ids=[issue_id],
            documents=[doc],
            metadatas=[{
                "system": system,
                "severity": severity,
                "resolved": bool(resolution),
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "metadata": json.dumps(metadata or {})
            }]
        )
        
        return issue_id
    
    def store_investigation(
        self,
        system: str,
        issue_description: str,
        commands: List[str],
        output: str,
        timestamp: str = None
    ) -> str:
        """Store investigation results for an issue"""
        if timestamp is None:
            timestamp = datetime.now(timezone.utc).isoformat()
        
        investigation_id = f"investigation_{system}_{datetime.now(timezone.utc).timestamp()}"
        
        doc = f"""
System: {system}
Issue: {issue_description}
Commands executed: {', '.join(commands)}
Output:
{output[:2000]}  # Limit output to prevent token overflow
"""
        
        self.issues_collection.add(
            ids=[investigation_id],
            documents=[doc],
            metadatas=[{
                "system": system,
                "issue": issue_description,
                "type": "investigation",
                "commands": json.dumps(commands),
                "timestamp": timestamp,
                "metadata": json.dumps({"output_length": len(output)})
            }]
        )
        
        return investigation_id
    
    def get_recent_investigations(
        self,
        issue_description: str,
        system: str,
        hours: int = 24
    ) -> List[Dict[str, Any]]:
        """Get recent investigations for a similar issue"""
        # Query for similar issues
        try:
            result = self.issues_collection.query(
                query_texts=[f"System: {system}\nIssue: {issue_description}"],
                n_results=10,
                where={"type": "investigation"},
                include=["documents", "metadatas", "distances"]
            )
            
            investigations = []
            if result['ids'] and result['ids'][0]:
                cutoff_time = datetime.now(timezone.utc).timestamp() - (hours * 3600)
                
                for i, doc_id in enumerate(result['ids'][0]):
                    meta = result['metadatas'][0][i]
                    timestamp = datetime.fromisoformat(meta['timestamp'])
                    
                    # Only include recent investigations
                    if timestamp.timestamp() > cutoff_time:
                        investigations.append({
                            "id": doc_id,
                            "system": meta['system'],
                            "issue": meta['issue'],
                            "commands": json.loads(meta['commands']),
                            "output": result['documents'][0][i],
                            "timestamp": meta['timestamp'],
                            "relevance": 1 - result['distances'][0][i]
                        })
            
            return investigations
        except Exception as e:
            print(f"Error querying investigations: {e}")
            return []
    
    def find_similar_issues(
        self,
        issue_description: str,
        system: Optional[str] = None,
        n_results: int = 5
    ) -> List[Dict[str, Any]]:
        """Find similar past issues using semantic search"""
        where = {"system": system} if system else None
        
        results = self.issues_collection.query(
            query_texts=[issue_description],
            n_results=n_results,
            where=where,
            include=["documents", "metadatas", "distances"]
        )
        
        similar = []
        for i, doc in enumerate(results['documents'][0]):
            similar.append({
                "issue": doc,
                "metadata": results['metadatas'][0][i],
                "similarity": 1 - results['distances'][0][i]  # Convert distance to similarity
            })
        
        return similar
    
    # ============ AI Decisions ============
    
    def store_decision(
        self,
        system: str,
        analysis: Dict[str, Any],
        action: Dict[str, Any],
        outcome: Dict[str, Any] = None
    ):
        """Store an AI decision for learning"""
        decision_id = f"decision_{datetime.now(timezone.utc).timestamp()}"
        
        doc = f"""
System: {system}
Status: {analysis.get('status', 'unknown')}
Assessment: {analysis.get('overall_assessment', '')}
Action: {action.get('proposed_action', '')}
Risk: {action.get('risk_level', 'unknown')}
Outcome: {outcome.get('status', 'pending') if outcome else 'pending'}
"""
        
        self.decisions_collection.add(
            ids=[decision_id],
            documents=[doc],
            metadatas=[{
                "system": system,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "analysis": json.dumps(analysis),
                "action": json.dumps(action),
                "outcome": json.dumps(outcome or {})
            }]
        )
    
    def get_recent_decisions(
        self,
        system: Optional[str] = None,
        n_results: int = 10
    ) -> List[Dict[str, Any]]:
        """Get recent decisions, optionally filtered by system"""
        where = {"system": system} if system else None
        
        results = self.decisions_collection.query(
            query_texts=["recent decisions"],
            n_results=n_results,
            where=where,
            include=["documents", "metadatas"]
        )
        
        decisions = []
        for i, doc in enumerate(results['documents'][0]):
            meta = results['metadatas'][0][i]
            decisions.append({
                "system": meta["system"],
                "timestamp": meta["timestamp"],
                "analysis": json.loads(meta["analysis"]),
                "action": json.loads(meta["action"]),
                "outcome": json.loads(meta["outcome"])
            })
        
        return decisions
    
    # ============ Context Generation for AI ============
    
    def get_system_context(self, hostname: str, git_context=None) -> str:
        """Generate rich context about a system for AI prompts"""
        context_parts = []
        
        # System info
        system = self.get_system(hostname)
        if system:
            context_parts.append(f"System: {hostname} ({system['type']})")
            context_parts.append(f"Services: {', '.join(system['services'])}")
            if system['capabilities']:
                context_parts.append(f"Capabilities: {', '.join(system['capabilities'])}")
        
        # Git repository info
        if system and system.get('metadata'):
            metadata = json.loads(system['metadata']) if isinstance(system['metadata'], str) else system['metadata']
            config_repo = metadata.get('config_repo', '')
            if config_repo:
                context_parts.append(f"\nConfiguration Repository: {config_repo}")
        
        # Recent git changes for this system
        if git_context:
            try:
                # Extract system name from FQDN
                system_name = hostname.split('.')[0]
                git_summary = git_context.get_system_context_summary(system_name)
                if git_summary:
                    context_parts.append(f"\n{git_summary}")
            except:
                pass
        
        # Dependencies
        deps = self.get_dependencies(hostname)
        if deps:
            context_parts.append("\nDependencies:")
            for dep in deps:
                context_parts.append(f"  - Depends on {dep['target']} for {dep['type']}")
        
        # Dependents
        dependents = self.get_dependents(hostname)
        if dependents:
            context_parts.append("\nUsed by:")
            for dependent in dependents:
                context_parts.append(f"  - {dependent['source']} uses this for {dependent['type']}")
        
        return "\n".join(context_parts)
    
    def get_issue_context(self, issue_description: str, system: str) -> str:
        """Get context about similar past issues"""
        similar = self.find_similar_issues(issue_description, system, n_results=3)
        
        if not similar:
            return ""
        
        context_parts = ["Similar past issues:"]
        for i, issue in enumerate(similar, 1):
            if issue['similarity'] > 0.7:  # Only include if fairly similar
                context_parts.append(f"\n{i}. {issue['issue']}")
                context_parts.append(f"   Similarity: {issue['similarity']:.2%}")
        
        return "\n".join(context_parts) if len(context_parts) > 1 else ""
    
    # ============ Config Files (for RAG) ============
    
    def store_config_file(
        self,
        file_path: str,
        content: str,
        category: str = "unknown",
        systems_using: List[str] = None
    ):
        """
        Store a configuration file for RAG retrieval
        
        Args:
            file_path: Path relative to repo root (e.g., "apps/gotify.nix")
            content: Full file contents
            category: apps/systems/osconfigs/users
            systems_using: List of system hostnames that import this file
        """
        self.config_files_collection.upsert(
            ids=[file_path],
            documents=[content],
            metadatas=[{
                "path": file_path,
                "category": category,
                "systems": json.dumps(systems_using or []),
                "updated_at": datetime.now(timezone.utc).isoformat()
            }]
        )
    
    def get_config_file(self, file_path: str) -> Optional[Dict[str, Any]]:
        """Get a specific config file by path"""
        try:
            result = self.config_files_collection.get(
                ids=[file_path],
                include=["documents", "metadatas"]
            )
            
            if result['ids']:
                return {
                    "path": file_path,
                    "content": result['documents'][0],
                    "metadata": result['metadatas'][0]
                }
        except:
            pass
        return None
    
    def query_config_files(
        self,
        query: str,
        system: str = None,
        category: str = None,
        n_results: int = 5
    ) -> List[Dict[str, Any]]:
        """
        Query config files using semantic search
        
        Args:
            query: Natural language query (e.g., "gotify configuration")
            system: Optional filter by system hostname
            category: Optional filter by category (apps/systems/etc)
            n_results: Number of results to return
            
        Returns:
            List of dicts with path, content, and metadata
        """
        where = {}
        if category:
            where["category"] = category
        
        try:
            result = self.config_files_collection.query(
                query_texts=[query],
                n_results=n_results,
                where=where if where else None,
                include=["documents", "metadatas", "distances"]
            )
            
            configs = []
            if result['ids'] and result['ids'][0]:
                for i, doc_id in enumerate(result['ids'][0]):
                    config = {
                        "path": doc_id,
                        "content": result['documents'][0][i],
                        "metadata": result['metadatas'][0][i],
                        "relevance": 1 - result['distances'][0][i]  # Convert distance to relevance
                    }
                    
                    # Filter by system if specified
                    if system:
                        systems = json.loads(config['metadata'].get('systems', '[]'))
                        if system not in systems:
                            continue
                    
                    configs.append(config)
            
            return configs
        except Exception as e:
            print(f"Error querying config files: {e}")
            return []
    
    def get_system_config_files(self, system: str) -> List[str]:
        """Get all config file paths used by a system"""
        # This is stored in the system's metadata now
        system_info = self.get_system(system)
        if system_info and 'config_files' in system_info.get('metadata', {}):
            # metadata is already a dict, config_files is already a list
            return system_info['metadata']['config_files']
        return []
    
    def update_system_config_files(self, system: str, config_files: List[str]):
        """Update the list of config files used by a system"""
        system_info = self.get_system(system)
        if system_info:
            # metadata is already a dict from get_system(), no need to json.loads()
            metadata = system_info.get('metadata', {})
            metadata['config_files'] = config_files
            metadata['config_updated_at'] = datetime.now(timezone.utc).isoformat()
            
            # Re-register with updated metadata
            self.register_system(
                hostname=system,
                system_type=system_info['type'],
                services=system_info['services'],
                capabilities=system_info.get('capabilities', []),
                metadata=metadata,
                config_repo=system_info.get('config_repo'),
                config_branch=system_info.get('config_branch')
            )
    
    # =========================================================================
    # ISSUE TRACKING
    # =========================================================================
    
    def store_issue(self, issue: Dict[str, Any]):
        """Store a new issue in the database"""
        issue_id = issue['issue_id']
        
        # Store in ChromaDB with the issue as document
        self.issues_collection.add(
            documents=[json.dumps(issue)],
            metadatas=[{
                'issue_id': issue_id,
                'hostname': issue['hostname'],
                'title': issue['title'],
                'status': issue['status'],
                'severity': issue['severity'],
                'created_at': issue['created_at'],
                'source': issue['source']
            }],
            ids=[issue_id]
        )
    
    def get_issue(self, issue_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve an issue by ID"""
        try:
            results = self.issues_collection.get(ids=[issue_id])
            if results['documents']:
                return json.loads(results['documents'][0])
            return None
        except Exception as e:
            print(f"Error retrieving issue {issue_id}: {e}")
            return None
    
    def update_issue(self, issue: Dict[str, Any]):
        """Update an existing issue"""
        issue_id = issue['issue_id']
        
        # Delete old version
        try:
            self.issues_collection.delete(ids=[issue_id])
        except:
            pass
        
        # Store updated version
        self.store_issue(issue)
    
    def delete_issue(self, issue_id: str):
        """Remove an issue from the database (used when archiving)"""
        try:
            self.issues_collection.delete(ids=[issue_id])
        except Exception as e:
            print(f"Error deleting issue {issue_id}: {e}")
    
    def list_issues(
        self,
        hostname: Optional[str] = None,
        status: Optional[str] = None,
        severity: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """List issues with optional filters"""
        try:
            # Build query filter
            where_filter = {}
            if hostname:
                where_filter['hostname'] = hostname
            if status:
                where_filter['status'] = status
            if severity:
                where_filter['severity'] = severity
            
            if where_filter:
                results = self.issues_collection.get(where=where_filter)
            else:
                results = self.issues_collection.get()
            
            issues = []
            for doc in results['documents']:
                issues.append(json.loads(doc))
            
            # Sort by created_at descending
            issues.sort(key=lambda x: x.get('created_at', ''), reverse=True)
            
            return issues
        except Exception as e:
            print(f"Error listing issues: {e}")
            return []
    
    # ============ Knowledge Base ============
    
    def store_knowledge(
        self,
        topic: str,
        knowledge: str,
        category: str = "general",
        source: str = "experience",
        confidence: str = "medium",
        tags: list = None
    ) -> str:
        """
        Store a piece of operational knowledge
        
        Args:
            topic: Main subject (e.g., "nixos-rebuild switch", "systemd-journal-remote")
            knowledge: The actual knowledge/insight/pattern
            category: Type of knowledge (command, pattern, troubleshooting, performance, etc.)
            source: Where this came from (experience, documentation, user-provided)
            confidence: How confident we are (low, medium, high)
            tags: Optional tags for categorization
        
        Returns:
            Knowledge ID
        """
        import uuid
        from datetime import datetime
        
        knowledge_id = str(uuid.uuid4())
        
        knowledge_doc = {
            "id": knowledge_id,
            "topic": topic,
            "knowledge": knowledge,
            "category": category,
            "source": source,
            "confidence": confidence,
            "tags": tags or [],
            "created_at": datetime.now(timezone.utc).isoformat(),
            "last_verified": datetime.now(timezone.utc).isoformat(),
            "times_referenced": 0
        }
        
        try:
            self.knowledge_collection.add(
                ids=[knowledge_id],
                documents=[knowledge],
                metadatas=[{
                    "topic": topic,
                    "category": category,
                    "source": source,
                    "confidence": confidence,
                    "tags": json.dumps(tags or []),
                    "created_at": knowledge_doc["created_at"],
                    "full_doc": json.dumps(knowledge_doc)
                }]
            )
            return knowledge_id
        except Exception as e:
            print(f"Error storing knowledge: {e}")
            return None
    
    def query_knowledge(
        self,
        query: str,
        category: str = None,
        limit: int = 5
    ) -> list:
        """
        Query the knowledge base for relevant information
        
        Args:
            query: What to search for
            category: Optional category filter
            limit: Maximum results to return
        
        Returns:
            List of relevant knowledge entries
        """
        try:
            where_filter = {}
            if category:
                where_filter["category"] = category
            
            results = self.knowledge_collection.query(
                query_texts=[query],
                n_results=limit,
                where=where_filter if where_filter else None
            )
            
            knowledge_items = []
            if results and results['documents']:
                for i, doc in enumerate(results['documents'][0]):
                    metadata = results['metadatas'][0][i]
                    full_doc = json.loads(metadata.get('full_doc', '{}'))
                    
                    # Increment reference count
                    full_doc['times_referenced'] = full_doc.get('times_referenced', 0) + 1
                    
                    knowledge_items.append(full_doc)
            
            return knowledge_items
        except Exception as e:
            print(f"Error querying knowledge: {e}")
            return []
    
    def get_knowledge_by_topic(self, topic: str) -> list:
        """Get all knowledge entries for a specific topic"""
        try:
            results = self.knowledge_collection.get(
                where={"topic": topic}
            )
            
            knowledge_items = []
            for metadata in results['metadatas']:
                full_doc = json.loads(metadata.get('full_doc', '{}'))
                knowledge_items.append(full_doc)
            
            return knowledge_items
        except Exception as e:
            print(f"Error getting knowledge by topic: {e}")
            return []
    
    def update_knowledge(
        self,
        knowledge_id: str,
        knowledge: str = None,
        confidence: str = None,
        verify: bool = False
    ):
        """
        Update an existing knowledge entry
        
        Args:
            knowledge_id: ID of knowledge to update
            knowledge: New knowledge text (optional)
            confidence: New confidence level (optional)
            verify: Mark as verified (updates last_verified timestamp)
        """
        from datetime import datetime
        
        try:
            # Get existing entry
            result = self.knowledge_collection.get(ids=[knowledge_id])
            if not result['documents']:
                return False
            
            metadata = result['metadatas'][0]
            full_doc = json.loads(metadata.get('full_doc', '{}'))
            
            # Update fields
            if knowledge:
                full_doc['knowledge'] = knowledge
            if confidence:
                full_doc['confidence'] = confidence
            if verify:
                full_doc['last_verified'] = datetime.now(timezone.utc).isoformat()
            
            # Update in collection
            self.knowledge_collection.update(
                ids=[knowledge_id],
                documents=[full_doc['knowledge']],
                metadatas=[{
                    "topic": full_doc['topic'],
                    "category": full_doc['category'],
                    "source": full_doc['source'],
                    "confidence": full_doc['confidence'],
                    "tags": json.dumps(full_doc['tags']),
                    "created_at": full_doc['created_at'],
                    "full_doc": json.dumps(full_doc)
                }]
            )
            return True
        except Exception as e:
            print(f"Error updating knowledge: {e}")
            return False
    
    def list_knowledge_topics(self, category: str = None) -> list:
        """List all unique topics in the knowledge base"""
        try:
            where_filter = {"category": category} if category else None
            results = self.knowledge_collection.get(where=where_filter)
            
            topics = set()
            for metadata in results['metadatas']:
                topics.add(metadata.get('topic'))
            
            return sorted(list(topics))
        except Exception as e:
            print(f"Error listing knowledge topics: {e}")
            return []


if __name__ == "__main__":
    import sys
    
    # Test the database
    db = ContextDatabase()
    
    # Register test systems
    db.register_system(
        "macha",
        "workstation",
        ["ollama"],
        capabilities=["ai-inference"]
    )
    
    db.register_system(
        "rhiannon",
        "server",
        ["gotify", "nextcloud", "prowlarr"],
        capabilities=["notifications", "cloud-storage"]
    )
    
    # Add relationship
    db.add_relationship(
        "macha",
        "rhiannon",
        "uses-service",
        "Macha uses Rhiannon's Gotify for notifications"
    )
    
    # Test queries
    print("All systems:", db.get_all_systems())
    print("\nMacha's dependencies:", db.get_dependencies("macha"))
    print("\nRhiannon's dependents:", db.get_dependents("rhiannon"))
    print("\nSystem context:", db.get_system_context("macha"))

