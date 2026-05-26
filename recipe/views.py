from rest_framework import generics, status
from rest_framework.permissions import AllowAny, IsAuthenticated
from django.shortcuts import get_object_or_404
from rest_framework.response import Response
from drf_spectacular.utils import extend_schema, OpenApiParameter
from django.db.models import Count

from .models import Recipe, RecipeLike
from .serializers import RecipeLikeSerializer, RecipeSerializer
from .permissions import IsAuthorOrReadOnly
from django.db.models import Q


@extend_schema(
    parameters=[
        OpenApiParameter(
            name='search',
            type=str,
            location='query',
            description='Поиск по названию, описанию или ингредиентам'
        ),
        OpenApiParameter(
            name='category__name',
            type=str,
            location='query',
            description='Фильтр по названию категории'
        ),
        OpenApiParameter(
            name='author__username',
            type=str,
            location='query',
            description='Фильтр по имени автора'
        ),
    ]
)
class RecipeListAPIView(generics.ListAPIView):
    serializer_class = RecipeSerializer
    permission_classes = (AllowAny,)
    filterset_fields = ('category__name', 'author__username')
    
    def get_queryset(self):
        queryset = Recipe.objects.annotate(
            likes_count=Count('recipelike')
        ).select_related('author', 'category')
        
        # Поиск
        search = self.request.query_params.get('search', None)
        if search:
            queryset = queryset.filter(
                Q(title__icontains=search) |
                Q(desc__icontains=search) |
                Q(ingredients__icontains=search)
            )
        
        # Сортировка
        ordering = self.request.query_params.get('ordering', None)
        if ordering:
            # Преобразуем имена полей для сортировки по аннотированным полям
            if ordering == 'total_number_of_likes':
                queryset = queryset.order_by('likes_count')
            elif ordering == '-total_number_of_likes':
                queryset = queryset.order_by('-likes_count')
            elif ordering == 'cook_time':
                queryset = queryset.order_by('cook_time')
            elif ordering == '-cook_time':
                queryset = queryset.order_by('-cook_time')
            else:
                queryset = queryset.order_by(ordering)
        
        return queryset


class RecipeCreateAPIView(generics.CreateAPIView):
    """
    Create: a recipe
    """
    queryset = Recipe.objects.all()
    serializer_class = RecipeSerializer
    permission_classes = (IsAuthenticated,)

    def perform_create(self, serializer):
        serializer.save(author=self.request.user)


class RecipeAPIView(generics.RetrieveUpdateDestroyAPIView):
    """
    Get, Update, Delete a recipe
    """
    queryset = Recipe.objects.all()
    serializer_class = RecipeSerializer
    permission_classes = (IsAuthorOrReadOnly,)


class RecipeLikeAPIView(generics.CreateAPIView):
    """
    Like, Dislike a recipe
    """
    serializer_class = RecipeLikeSerializer
    permission_classes = (IsAuthenticated,)

    def post(self, request, pk):
        recipe = get_object_or_404(Recipe, id=self.kwargs['pk'])
        new_like, created = RecipeLike.objects.get_or_create(
            user=request.user, recipe=recipe)
        if created:
            new_like.save()
            return Response(status=status.HTTP_201_CREATED)
        return Response(status=status.HTTP_400_BAD_REQUEST)

    def delete(self, request, pk):
        recipe = get_object_or_404(Recipe, id=self.kwargs['pk'])
        like = RecipeLike.objects.filter(user=request.user, recipe=recipe)
        if like.exists():
            like.delete()
            return Response(status=status.HTTP_200_OK)
        return Response(status=status.HTTP_400_BAD_REQUEST)

    def perform_create(self, serializer):
        serializer.save(author=self.request.user)
